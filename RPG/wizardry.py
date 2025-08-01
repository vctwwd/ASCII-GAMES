from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
import curses
import json
import math
import time


# ====================== 1. 渲染组件 ======================
class RenderContext:
    """渲染上下文，封装渲染所需参数"""

    def __init__(self, side, ray_dir_x, ray_dir_y, wall_x, distance, player_dir_x, player_dir_y):
        self.side = side  # 碰撞面（0-垂直，1-水平）
        self.ray_dir_x = ray_dir_x
        self.ray_dir_y = ray_dir_y
        self.wall_x = wall_x  # 墙面X坐标（0-1）
        self.distance = distance  # 到墙面的距离
        self.player_dir_x = player_dir_x  # 玩家方向向量X
        self.player_dir_y = player_dir_y  # 玩家方向向量Y


class Raycaster:
    """光线投射类"""

    def __init__(self, game_map):
        self.game_map = game_map
        self.pos_x = self.pos_y = 1.5
        self.dir_x, self.dir_y = 1, 0
        self.plane_x, self.plane_y = 0, -0.66
        self.move_distance = 1.0
        self.rotate_angle = math.pi / 2
        self.target_dir_x = self.dir_x
        self.target_dir_y = self.dir_y
        self.target_plane_x = self.plane_x
        self.target_plane_y = self.plane_y
        self.rotating = False
        self.rotation_speed = 0.2
        self.rotation_progress = 0.0

    def rotate(self, clockwise=True):
        rot = self.rotate_angle * (-1 if clockwise else 1)
        self.target_dir_x = self.dir_x * math.cos(rot) - self.dir_y * math.sin(rot)
        self.target_dir_y = self.dir_x * math.sin(rot) + self.dir_y * math.cos(rot)
        self.target_plane_x = self.plane_x * math.cos(rot) - self.plane_y * math.sin(rot)
        self.target_plane_y = self.plane_x * math.sin(rot) + self.plane_y * math.cos(rot)
        self.rotating = True
        self.rotation_progress = 0.0

    def update_rotation(self):
        if not self.rotating: return
        self.rotation_progress += self.rotation_speed
        if self.rotation_progress >= 1.0:
            self.dir_x, self.dir_y = self.target_dir_x, self.target_dir_y
            self.plane_x, self.plane_y = self.target_plane_x, self.target_plane_y
            self.rotating = False
            return
        self.dir_x = self.dir_x * (1 - self.rotation_progress) + self.target_dir_x * self.rotation_progress
        self.dir_y = self.dir_y * (1 - self.rotation_progress) + self.target_dir_y * self.rotation_progress
        self.plane_x = self.plane_x * (1 - self.rotation_progress) + self.target_plane_x * self.rotation_progress
        self.plane_y = self.plane_y * (1 - self.rotation_progress) + self.target_plane_y * self.rotation_progress

    def move(self, forward=True):
        move = self.move_distance * (1 if forward else -1)
        new_x = self.pos_x + self.dir_x * move
        new_y = self.pos_y + self.dir_y * move
        if not self.game_map.is_wall(int(new_x), int(new_y)):
            self.pos_x = int(new_x) + 0.5
            self.pos_y = int(new_y) + 0.5

    def get_front_cell(self):
        front_x = int(self.pos_x + self.dir_x * 0.7)
        front_y = int(self.pos_y + self.dir_y * 0.7)
        return self.game_map.get_cell(front_x, front_y)


class RaycastResult:
    """封装光线投射结果，提供统一渲染接口"""

    def __init__(self, cell, side, ray_dir_x, ray_dir_y, wall_x, distance, player_dir_x, player_dir_y):
        self.cell = cell
        self.side = side
        self.ray_dir_x = ray_dir_x
        self.ray_dir_y = ray_dir_y
        self.wall_x = wall_x
        self.distance = distance
        self.player_dir_x = player_dir_x
        self.player_dir_y = player_dir_y

    def render(self):
        context = RenderContext(
            side=self.side,
            ray_dir_x=self.ray_dir_x,
            ray_dir_y=self.ray_dir_y,
            wall_x=self.wall_x,
            distance=self.distance,
            player_dir_x=self.player_dir_x,
            player_dir_y=self.player_dir_y
        )
        return self.cell.renderer.render_3d(context)


class CellRenderer(ABC):
    """单元格渲染组件基类"""

    @abstractmethod
    def render_3d(self, context: RenderContext) -> str: pass

    @abstractmethod
    def get_minimap_char(self) -> str: pass


class WallRenderer(CellRenderer):
    TEXTURE_LIB = {
        "outer_wall_vertical": "|",
        "outer_wall_horizontal": "-",
        "inner_wall_vertical": "|",
        "inner_wall_horizontal": "-",
    }

    def __init__(self, texture_id):
        self.texture_id = texture_id

    def render_3d(self, context: RenderContext) -> str:
        # 计算墙面法向量
        if context.side == 0:  # 垂直面
            wall_normal_x = 1 if context.ray_dir_x >= 0 else -1
            wall_normal_y = 0
        else:  # 水平面
            wall_normal_x = 0
            wall_normal_y = 1 if context.ray_dir_y >= 0 else -1

        # 计算视线方向与法向量的夹角余弦值
        dot_product = (context.player_dir_x * wall_normal_x +
                      context.player_dir_y * wall_normal_y)

        # 修正后的逻辑：
        if abs(dot_product) > 0.5:  # 法向量与视线方向夹角小于60度 -> 正对墙面
            return self.TEXTURE_LIB[f"{self.texture_id}_horizontal"]  # 水平图案
        else:  # 侧面墙面
            return self.TEXTURE_LIB[f"{self.texture_id}_vertical"]    # 垂直图案

    def get_minimap_char(self):
        return "#"


class DoorRenderer(CellRenderer):
    """门渲染组件实现"""

    def __init__(self, behavior):
        self.behavior = behavior

    def render_3d(self, context: RenderContext) -> str:
        # 计算玩家视线方向与门法向量的角度
        door_normal_x = 0
        door_normal_y = 0

        if context.side == 0:  # 垂直门
            door_normal_x = 1 if context.ray_dir_x >= 0 else -1
        else:  # 水平门
            door_normal_y = 1 if context.ray_dir_y >= 0 else -1

        # 计算点积判断门的方向
        dot_product = (context.player_dir_x * door_normal_x +
                       context.player_dir_y * door_normal_y)

        # 确定门的方向
        door_direction = "vertical" if abs(dot_product) < 0.5 else "horizontal"

        frame_thickness = 0.15 if context.distance >= 1.5 else 0.25
        if context.wall_x < frame_thickness or context.wall_x > 1 - frame_thickness:
            return "▐"

        if self.behavior.door_animating:
            threshold = 0.5 * (self.behavior.door_animation_progress
                               if self.behavior.door_animation_type == "opening"
                               else 1 - self.behavior.door_animation_progress)
            if context.wall_x < 0.5 - threshold or context.wall_x > 0.5 + threshold:
                return "|" if door_direction == "vertical" else "-"
            return " "

        return " " if self.behavior.door_open else "|" if door_direction == "vertical" else "-"

    def get_minimap_char(self):
        return " " if self.behavior.door_open else "+"


class FloorRenderer(CellRenderer):
    """普通地板渲染组件实现"""

    def render_3d(self, context: RenderContext) -> str: return " "

    def get_minimap_char(self): return "."


class InteractiveFloorRenderer(CellRenderer):
    """互动地板渲染组件实现"""

    def __init__(self, behavior):
        self.behavior = behavior

    def render_3d(self, context: RenderContext) -> str: return " "

    def get_minimap_char(self): return "*" if self.behavior.triggered else "."


# ====================== 2. 动画组件 ======================
class Animation(ABC):
    """动画基类"""

    def __init__(self, duration):
        self.duration = duration
        self.elapsed_time = 0.0
        self.completed = False

    def update(self, delta_time):
        """更新动画状态"""
        self.elapsed_time += delta_time
        if self.elapsed_time >= self.duration:
            self.completed = True

    @abstractmethod
    def render(self, stdscr, game):
        """渲染动画"""
        pass


class FlashAnimation(Animation):
    """闪屏动画实现"""

    def __init__(self):
        super().__init__(duration=0.5)  # 持续0.5秒

    def render(self, stdscr, game):
        """渲染闪屏效果"""
        if int(self.elapsed_time * 10) % 2 == 0:  # 每0.1秒切换一次
            height, width = stdscr.getmaxyx()
            for y in range(height):
                try:
                    stdscr.addstr(y, 0, "#" * (width - 1))
                except:
                    pass


class InventoryTransitionAnimation(Animation):
    """物品栏过渡动画（调整为0.5秒）"""

    def __init__(self, is_entering=True):
        super().__init__(duration=0.5)  # 调整为0.5秒
        self.is_entering = is_entering

    def render(self, stdscr, game):
        """渲染淡入淡出效果（覆盖整个画面）"""
        height, width = stdscr.getmaxyx()
        progress = min(1.0, self.elapsed_time / self.duration)

        # 计算渐变系数（进入时从0到1，退出时从1到0）
        alpha = progress if self.is_entering else 1.0 - progress

        # 创建覆盖整个画面的覆盖层
        for y in range(height):
            for x in range(width):
                try:
                    # 根据透明度选择字符
                    if alpha < 0.2:
                        char = " "
                    elif alpha < 0.4:
                        char = "░"
                    elif alpha < 0.6:
                        char = "▒"
                    elif alpha < 0.8:
                        char = "▓"
                    else:
                        char = "█"
                    stdscr.addch(y, x, char)
                except:
                    pass


class AnimationRenderer:
    """动画渲染管理器"""

    def __init__(self):
        self.active_animations = []

    def add_animation(self, animation):
        """添加新动画"""
        self.active_animations.append(animation)

    def update(self, delta_time):
        """更新所有动画状态"""
        # 更新所有动画
        for animation in self.active_animations[:]:
            animation.update(delta_time)
            if animation.completed:
                self.active_animations.remove(animation)

    def render(self, stdscr, game):
        """渲染所有活动动画"""
        for animation in self.active_animations:
            animation.render(stdscr, game)


# ====================== 3. 行为组件 ======================
class CellBehavior(ABC):
    """单元格行为策略基类"""

    @abstractmethod
    def update(self, delta_time): pass

    @abstractmethod
    def on_interact(self, game, x, y): pass

    @abstractmethod
    def on_player_step(self, game, x, y): pass


class DoorBehavior(CellBehavior):
    """门的行为策略实现"""

    def __init__(self):
        self.door_open = False
        self.door_animating = False
        self.door_animation_type = None
        self.door_animation_progress = 0.0

    def update(self, delta_time):
        if self.door_animating:
            self.door_animation_progress += delta_time * 2.0
            if self.door_animation_progress >= 1.0:
                self.door_animating = False
                self.door_open = not self.door_open
                self.door_animation_type = None

    def on_interact(self, game, x, y):
        if not self.door_animating:
            self.door_animating = True
            self.door_animation_progress = 0.0
            if self.door_open:
                self.door_animation_type = "closing"
            else:
                self.door_animation_type = "opening"

    def on_player_step(self, game, x, y):
        pass


class InteractiveFloorBehavior(CellBehavior):
    """互动地板行为策略实现"""

    def __init__(self, effect_type=None, can_retrigger=False):
        self.effect_type = effect_type
        self.can_retrigger = can_retrigger
        self.triggered = False
        self.trigger_time = 0

    def update(self, delta_time): pass

    def on_interact(self, game, x, y): pass

    def on_player_step(self, game, x, y):
        if not self.triggered or self.can_retrigger:
            self.triggered = True
            self.trigger_time = time.time()
            game.animation_renderer.add_animation(FlashAnimation())
            return True
        return False


# ====================== 4. 访问组件 ======================
class MapVisitor(ABC):
    """地图访问者基类"""

    @abstractmethod
    def visit_cell(self, cell, x, y): pass


class AnimationUpdater(MapVisitor):
    """动画更新访问者实现"""

    def __init__(self, delta_time):
        self.delta_time = delta_time

    def visit_cell(self, cell, x, y):
        if cell.behavior:
            cell.behavior.update(self.delta_time)


class InteractionHandler(MapVisitor):
    """交互处理访问者实现"""

    def __init__(self, game, x, y):
        self.game = game
        self.x = x
        self.y = y

    def visit_cell(self, cell, x, y):
        if x == self.x and y == self.y and cell.behavior:
            cell.behavior.on_interact(self.game, x, y)


class StepHandler(MapVisitor):
    """玩家踏步处理访问者实现"""

    def __init__(self, game, x, y):
        self.game = game
        self.x = x
        self.y = y

    def visit_cell(self, cell, x, y):
        if x == self.x and y == self.y and cell.behavior:
            cell.behavior.on_player_step(self.game, x, y)


# ====================== 5. 状态组件 ======================
class StatusInfoProvider(ABC):
    """状态信息提供者基类"""

    @abstractmethod
    def get_status_info(self, game, x, y) -> str: pass


class DoorStatusProvider(StatusInfoProvider):
    """门状态信息提供者实现"""

    def get_status_info(self, game, x, y) -> str:
        front_cell = game.raycaster.get_front_cell()
        if not front_cell or not isinstance(front_cell.behavior, DoorBehavior):
            return ""

        behavior = front_cell.behavior
        if behavior.door_animating:
            return " [门状态变化中]" if not behavior.door_animation_type else \
                " [开门中]" if behavior.door_animation_type == "opening" else " [关门中]"
        return " [门已开]" if behavior.door_open else " [门前]"


class FloorStatusProvider(StatusInfoProvider):
    """地板状态信息提供者实现"""

    def get_status_info(self, game, x, y) -> str:
        current_cell = game.game_map.get_cell(x, y)
        if not current_cell or not isinstance(current_cell.behavior, InteractiveFloorBehavior):
            return ""
        return " [互动地板]" + ("已触发" if current_cell.behavior.triggered else "未触发")


# ====================== 6. 地图单元格 ======================
class MapCell:
    """通用地图单元格"""

    def __init__(self, is_wall=False, texture_id="floor", behavior=None, renderer=None):
        self.is_wall = is_wall
        self.texture_id = texture_id
        self.behavior = behavior
        self.renderer = renderer

    def accept_visitor(self, visitor, x, y):
        visitor.visit_cell(self, x, y)

    def get_minimap_char(self):
        return self.renderer.get_minimap_char() if self.renderer else "#" if self.is_wall else "."


class CellFactory:
    """单元格创建工厂"""

    @staticmethod
    def create_wall(texture_id="outer_wall"):
        return MapCell(
            is_wall=True,
            texture_id=texture_id,
            renderer=WallRenderer(texture_id)
        )

    @staticmethod
    def create_door():
        behavior = DoorBehavior()
        return MapCell(
            is_wall=True,
            texture_id="door",
            behavior=behavior,
            renderer=DoorRenderer(behavior)
        )

    @staticmethod
    def create_floor():
        return MapCell(
            is_wall=False,
            renderer=FloorRenderer()
        )

    @staticmethod
    def create_interactive_floor(can_retrigger=False):
        behavior = InteractiveFloorBehavior(can_retrigger=can_retrigger)
        return MapCell(
            is_wall=False,
            behavior=behavior,
            renderer=InteractiveFloorRenderer(behavior)
        )


class GameMap:
    """游戏地图类"""

    def __init__(self, width=10, height=10):
        self.width = width
        self.height = height
        self.grid = [[CellFactory.create_floor() for _ in range(width)] for _ in range(height)]

    def generate_default_map(self):
        # 创建外边界墙
        for i in range(self.height):
            self.grid[i][0] = CellFactory.create_wall("outer_wall")
            self.grid[i][self.width - 1] = CellFactory.create_wall("outer_wall")
        for j in range(self.width):
            self.grid[0][j] = CellFactory.create_wall("outer_wall")
            self.grid[self.height - 1][j] = CellFactory.create_wall("outer_wall")

        # 创建中间墙和门
        wall_row = self.height // 2
        for j in range(3, 8):
            self.grid[wall_row][j] = CellFactory.create_door() if j == 5 else CellFactory.create_wall("inner_wall")

        # 添加互动地板
        self.grid[3][3] = CellFactory.create_interactive_floor(can_retrigger=True)
        self.grid[7][7] = CellFactory.create_interactive_floor(can_retrigger=False)

    def is_valid_position(self, x, y):
        return 0 <= x < self.height and 0 <= y < self.width

    def is_wall(self, x, y):
        if not self.is_valid_position(x, y): return True
        cell = self.grid[x][y]
        return cell.is_wall and not (isinstance(cell.behavior, DoorBehavior) and cell.behavior.door_open)

    def get_cell(self, x, y):
        return self.grid[x][y] if self.is_valid_position(x, y) else None

    def accept_visitor(self, visitor):
        for i in range(self.height):
            for j in range(self.width):
                self.grid[i][j].accept_visitor(visitor, i, j)


# ====================== 7. 物品系统 ======================
@dataclass
class ItemEffect:
    """物品效果定义"""
    effect_type: str  # health/sp/exp/attack/defense/function 等
    value: Union[int, str]  # 数值或函数名
    args: List[Any] = field(default_factory=list)  # 函数参数
    kwargs: Dict[str, Any] = field(default_factory=dict)  # 关键字参数


@dataclass
class ItemDefinition:
    """物品定义（对应JSON中的条目）"""
    id: int
    name: str
    description: str
    item_type: str  # consumable/equipment/material
    icon: str
    max_stack: int = 1
    slot: Optional[str] = None  # 装备部位 (weapon/armor/accessory)
    usage_type: str = "single"  # single/infinite (消耗品使用次数)
    effects: List[ItemEffect] = field(default_factory=list)


class Item:
    """物品实例"""

    def __init__(self, definition: ItemDefinition, count: int = 1):
        self.definition = definition
        self.count = count
        self.equipped = False  # 是否装备

    @property
    def id(self):
        return self.definition.id

    @property
    def name(self):
        return self.definition.name

    @property
    def description(self):
        return self.definition.description

    @property
    def item_type(self):
        return self.definition.item_type

    @property
    def icon(self):
        return self.definition.icon

    @property
    def max_stack(self):
        return self.definition.max_stack

    @property
    def slot(self):
        return self.definition.slot

    @property
    def usage_type(self):
        return self.definition.usage_type

    def get_display_info(self):
        """获取显示信息"""
        return f"{self.icon} {self.name} x{self.count}"

    def get_full_info(self):
        """获取完整信息（用于详情显示）"""
        info = [
            f"名称: {self.name}",
            f"类型: {self.get_type_name()}",
            f"描述: {self.description}",
            f"数量: {self.count}/{self.max_stack}"
        ]

        if self.item_type == "consumable":
            info.append(f"使用次数: {'无限' if self.usage_type == 'infinite' else '1次'}")

        if self.item_type == "equipment" and self.slot:
            info.append(f"装备部位: {self.get_slot_name()}")
            info.append(f"装备状态: {'已装备' if self.equipped else '未装备'}")

        if self.definition.effects:
            info.append("效果:")
            for effect in self.definition.effects:
                effect_name = {
                    "health": "生命值",
                    "sp": "技能值",
                    "exp": "经验值",
                    "attack": "攻击力",
                    "defense": "防御力"
                }.get(effect.effect_type, effect.effect_type)
                info.append(f"  - {effect_name}: {effect.value:+}")

        return info

    def get_type_name(self):
        """获取类型名称（中文）"""
        return {
            "consumable": "消耗品",
            "equipment": "装备",
            "material": "材料"
        }.get(self.item_type, self.item_type)

    def get_slot_name(self):
        """获取装备部位名称（中文）"""
        return {
            "weapon": "武器",
            "armor": "护甲",
            "accessory": "饰品"
        }.get(self.slot, self.slot)


class ItemFactory:
    """物品工厂（根据JSON定义创建物品）"""

    _item_definitions: Dict[int, ItemDefinition] = {}
    _function_registry: Dict[str, Callable] = {}  # 函数注册表

    @classmethod
    def register_function(cls, name: str, func: Callable):
        """注册效果函数"""
        cls._function_registry[name] = func

    @classmethod
    def load_definitions(cls, json_file: str):
        """从JSON文件加载物品定义"""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                definitions = json.load(f)
        except FileNotFoundError:
            print(f"错误：物品定义文件 {json_file} 未找到。")
            definitions = []

        cls._item_definitions.clear()
        for item_data in definitions:
            # 创建效果列表
            effects = []
            for effect_data in item_data.get("effects", []):
                # 处理函数效果
                if effect_data["type"] == "function":
                    effect = ItemEffect(
                        effect_type="function",
                        value=effect_data["function"],
                        args=effect_data.get("args", []),
                        kwargs=effect_data.get("kwargs", {})
                    )
                else:
                    # 数值效果
                    effect = ItemEffect(
                        effect_type=effect_data["type"],
                        value=effect_data["value"]
                    )
                effects.append(effect)

            # 创建物品定义
            definition = ItemDefinition(
                id=item_data["id"],
                name=item_data["name"],
                description=item_data["description"],
                item_type=item_data["type"],
                icon=item_data["icon"],
                max_stack=item_data.get("max_stack", 1),
                slot=item_data.get("slot"),
                usage_type=item_data.get("usage_type", "single"),
                effects=effects
            )

            cls._item_definitions[item_data["id"]] = definition

    @classmethod
    def create_item(cls, item_id: int, count: int = 1) -> Optional[Item]:
        """创建物品实例"""
        if item_id in cls._item_definitions:
            return Item(cls._item_definitions[item_id], count)
        return None


ItemFactory.load_definitions("item.json")


class Inventory:
    """玩家物品栏（支持滚动）"""

    def __init__(self, capacity: int = 10):
        self.capacity = capacity  # 物品栏格数
        self.items: List[Item] = []  # 物品列表
        self.selected_index = 0  # 当前选中的物品索引
        self.scroll_offset = 0  # 滚动偏移量
        self.visible_slots = 8  # 可见物品槽位数量

    def add_item(self, item: Item) -> bool:
        """添加物品到物品栏"""
        # 尝试堆叠相同物品
        for existing in self.items:
            if existing.id == item.id and existing.count < existing.max_stack:
                stack_space = existing.max_stack - existing.count
                if item.count <= stack_space:
                    existing.count += item.count
                    return True
                else:
                    existing.count = existing.max_stack
                    item.count -= stack_space

        # 添加新物品
        if len(self.items) < self.capacity:
            self.items.append(item)
            return True
        return False

    def remove_item(self, index: int, count: int = 1) -> Optional[Item]:
        """移除物品"""
        if 0 <= index < len(self.items):
            item = self.items[index]

            # 无限使用物品不减少数量
            if item.item_type == "consumable" and item.usage_type == "infinite":
                return item

            if count >= item.count:
                removed = self.items.pop(index)
                # 调整选中索引
                if self.selected_index >= len(self.items):
                    self.selected_index = max(0, len(self.items) - 1)
                return removed
            else:
                item.count -= count
                return ItemFactory.create_item(item.id, count)
        return None

    def get_selected_item(self) -> Optional[Item]:
        """获取当前选中的物品"""
        if 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def move_selection(self, direction: str):
        """移动选择并处理滚动"""
        if not self.items:
            return

        if direction == "up":
            self.selected_index = max(0, self.selected_index - 1)
        elif direction == "down":
            self.selected_index = min(len(self.items) - 1, self.selected_index + 1)

        # 调整滚动位置，确保选中项在可见范围内
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + self.visible_slots:
            self.scroll_offset = self.selected_index - self.visible_slots + 1

    def get_visible_items(self) -> List[Item]:
        """获取当前可见的物品（根据滚动位置）"""
        start = self.scroll_offset
        end = min(start + self.visible_slots, len(self.items))
        return self.items[start:end]

    def equip_item(self, item: Item, game):
        """装备物品"""
        if item.item_type != "equipment" or not item.slot:
            return "无法装备此物品"

        # 检查是否已装备同部位物品
        for existing in self.items:
            if existing.equipped and existing.slot == item.slot:
                existing.equipped = False
                self._apply_equipment_effects(existing, game, remove=True)

        item.equipped = True
        self._apply_equipment_effects(item, game)
        return f"已装备 {item.name}"

    def unequip_item(self, item: Item, game):
        """卸下物品"""
        if not item.equipped:
            return "此物品未装备"

        item.equipped = False
        self._apply_equipment_effects(item, game, remove=True)
        return f"已卸下 {item.name}"

    def _apply_equipment_effects(self, item: Item, game, remove: bool = False):
        """应用或移除装备效果"""
        multiplier = -1 if remove else 1
        player = game.player_info

        for effect in item.definition.effects:
            if effect.effect_type == "health":
                player.max_health += effect.value * multiplier
                player.health = min(player.health, player.max_health)
            elif effect.effect_type == "sp":
                player.max_sp += effect.value * multiplier
                player.sp = min(player.sp, player.max_sp)
            elif effect.effect_type == "attack":
                player.attack += effect.value * multiplier
            elif effect.effect_type == "defense":
                player.defense += effect.value * multiplier
            elif effect.effect_type == "max_health":
                player.max_health += effect.value * multiplier
                player.health = min(player.health, player.max_health)
            elif effect.effect_type == "max_sp":
                player.max_sp += effect.value * multiplier
                player.sp = min(player.sp, player.max_sp)


# ====================== 8. 玩家信息 ======================
class PlayerInfo:
    """玩家信息单例类"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 在 __init__ 中初始化所有属性
            cls._instance.__init__()
        return cls._instance

    def __init__(self):
        """初始化所有玩家属性"""
        # 检查是否已经初始化，避免重复初始化
        if not hasattr(self, '_initialized'):
            # 基础属性
            self.health = 100
            self.max_health = 100
            self.sp = 10
            self.max_sp = 10
            self.level = 1
            self.exp = 0
            self.attack = 10  # 新增攻击属性
            self.defense = 10  # 新增防御属性

            # 物品栏
            self.inventory = Inventory(capacity=12)

            # 初始化一些示例物品
            self._init_default_items()

            # 其他属性
            self.observers = []
            self._initialized = True

    def reset(self):
        """重置玩家状态（保留观察者）"""
        self.health = 100
        self.max_health = 100
        self.sp = 10
        self.max_sp = 10
        self.level = 1
        self.exp = 0
        self.attack = 10  # 重置攻击
        self.defense = 10  # 重置防御

    @staticmethod
    def _exp_required_for_level(level):
        """计算升到指定等级所需的总经验值"""
        # 确保1级时经验需求为0
        if level <= 1:
            return 0
        # 基础经验函数：二次函数增长
        # 公式：f(level) = 100 * (level-1)^1.5
        return int(100 * (level - 1) ** 1.5)

    def get_level_up_exp(self):
        """获取升到下一级所需经验"""
        if self.level >= 100:
            return 0
        return self._exp_required_for_level(self.level + 1) - self._exp_required_for_level(self.level)

    def get_current_level_progress(self):
        """获取当前等级进度（0.0-1.0）"""
        if self.level >= 100:
            return 1.0

        # 计算当前等级已获得经验（确保非负）
        current_exp = max(0, self.exp - self._exp_required_for_level(self.level))
        level_up_exp = self.get_level_up_exp()

        # 避免除以零错误
        if level_up_exp <= 0:
            return 1.0

        return min(1.0, current_exp / level_up_exp)

    def add_exp(self, amount):
        """增加经验值（可能触发升级）"""
        self.exp += amount

        # 检查是否升级（支持连续升级）
        while self.level < 100 and self.exp >= self._exp_required_for_level(self.level + 1):
            self.change_level(1)  # 升一级

    def change_level(self, delta):
        """
        变更玩家等级（支持连续升级/降级）
        :param delta: 等级变化量（正数升级，负数降级）
        """
        if delta == 0:
            return

        # 确定操作方向和循环次数
        step = 1 if delta > 0 else -1
        steps = abs(delta)

        for _ in range(steps):
            if step > 0:  # 升级
                if self.level >= 100:
                    break  # 已达最高级
                self._level_up()
            else:  # 降级
                if self.level <= 1:
                    break  # 已达最低级
                self._level_down()

    def _level_up(self):
        """执行单次升级操作"""
        self.level += 1

        # 升级奖励
        self.max_health += 5
        self.health = self.max_health
        self.max_sp += 1
        self.sp = self.max_sp
        self.attack += 1  # 升级增加攻击
        self.defense += 1  # 升级增加防御

        # 保留当前经验值（不重置）
        self._notify_observers("level_up")

    def _level_down(self):
        """执行单次降级操作"""
        self.level -= 1

        # 降级惩罚
        self.max_health = max(50, self.max_health - 5)
        self.health = min(self.health, self.max_health)
        self.max_sp = max(5, self.max_sp - 1)
        self.sp = min(self.sp, self.max_sp)
        self.attack = max(5, self.attack - 1)  # 降级减少攻击
        self.defense = max(5, self.defense - 1)  # 降级减少防御

        # 降级后重置经验值为当前等级基础值
        self.exp = self._exp_required_for_level(self.level)
        self._notify_observers("level_down")

    def downgrade_level(self, levels=1):
        """降级指定等级数（默认为1级）"""
        self.change_level(-levels)

    def take_damage(self, amount):
        """受到伤害"""
        self.health = max(0, self.health - amount)
        self._notify_observers("health_changed")

    def heal(self, amount):
        """恢复生命值"""
        self.health = min(self.max_health, self.health + amount)
        self._notify_observers("health_changed")

    def use_sp(self, amount):
        """使用技能点"""
        if self.sp >= amount:
            self.sp -= amount
            self._notify_observers("sp_changed")
            return True
        return False

    def restore_sp(self, amount):
        """恢复技能点"""
        self.sp = min(self.max_sp, self.sp + amount)
        self._notify_observers("sp_changed")

    def _init_default_items(self):
        """初始化默认物品"""
        # 添加消耗品
        self.inventory.add_item(ItemFactory.create_item(1, 3))  # 治疗药剂 x3
        self.inventory.add_item(ItemFactory.create_item(2, 2))  # 魔法药剂 x2
        self.inventory.add_item(ItemFactory.create_item(3, 1))  # 无限面包 x1

        # 添加装备
        self.inventory.add_item(ItemFactory.create_item(4, 1))  # 铁剑
        self.inventory.add_item(ItemFactory.create_item(5, 1))  # 皮甲
        self.inventory.add_item(ItemFactory.create_item(6, 1))  # 银戒指

        # 添加材料
        self.inventory.add_item(ItemFactory.create_item(7, 5))  # 铁矿石 x5
        self.inventory.add_item(ItemFactory.create_item(8, 8))  # 草药 x8

    # 观察者模式预留接口
    def add_observer(self, observer):
        self.observers.append(observer)

    def _notify_observers(self, event_type):
        for observer in self.observers:
            observer.on_player_event(event_type, self)


# ====================== 9. 游戏渲染器 ======================
class StatusInfoManager:
    """状态信息管理器"""

    def __init__(self):
        self.providers = [DoorStatusProvider(), FloorStatusProvider()]

    def get_status_info(self, game) -> str:
        x, y = int(game.raycaster.pos_x), int(game.raycaster.pos_y)
        return "".join(provider.get_status_info(game, x, y) for provider in self.providers)


class GameRenderer:
    """游戏渲染器"""

    def __init__(self):
        self.status_manager = StatusInfoManager()
        self.boundary_wall = CellFactory.create_wall("outer_wall")
        self.player_info = PlayerInfo()

    def render_game(self, stdscr, game):
        """渲染游戏主画面"""
        height, width = stdscr.getmaxyx()
        stdscr.clear()

        # 定义边栏宽度
        sidebar_width = 30

        # 正常渲染流程
        render_height = height - 2
        render_width = width - sidebar_width

        # 3D视图渲染
        for x in range(render_width):
            # 计算光线方向
            camera_x = 2 * x / render_width - 1  # x坐标在屏幕上的位置，范围[-1,1]
            ray_dir_x = game.raycaster.dir_x + game.raycaster.plane_x * camera_x
            ray_dir_y = game.raycaster.dir_y + game.raycaster.plane_y * camera_x

            ray_result = self._cast_ray(game.raycaster, ray_dir_x, ray_dir_y)
            wall_char = ray_result.render()
            wall_height = min(int(render_height / ray_result.distance), int(render_height * 0.9))
            draw_start = max(1, render_height // 2 - wall_height // 2)
            draw_end = min(render_height, render_height // 2 + wall_height // 2)

            for y in range(draw_start, draw_end + 1):
                try:
                    stdscr.addch(y, x, wall_char)
                except:
                    pass

        # 状态栏渲染
        angle = math.degrees(math.atan2(-game.raycaster.dir_y, game.raycaster.dir_x))
        direction = "北" if 45 <= angle < 135 else "西" if 135 <= angle < 225 else "南" if 225 <= angle < 315 else "东"
        status = [
            f"位置: ({int(game.raycaster.pos_x)}, {int(game.raycaster.pos_y)}) 方向: {direction}",
            self.status_manager.get_status_info(game)
        ]
        try:
            stdscr.addstr(0, 0, "W:前进 A:左转 D:右转 S:向后转 空格:开门 Q:退出")
            stdscr.addstr(height - 2, 0, status[0])
            stdscr.addstr(height - 1, 0, status[1])
        except:
            pass

        # 小地图渲染
        self._render_minimap(stdscr, game.raycaster, render_width)

    def _cast_ray(self, raycaster, ray_dir_x, ray_dir_y):
        pos_x, pos_y = raycaster.pos_x, raycaster.pos_y
        map_x, map_y = int(pos_x), int(pos_y)

        ray_length_x = abs(1 / ray_dir_x) if ray_dir_x != 0 else float('inf')
        ray_length_y = abs(1 / ray_dir_y) if ray_dir_y != 0 else float('inf')

        step_x = 1 if ray_dir_x >= 0 else -1
        step_y = 1 if ray_dir_y >= 0 else -1

        if ray_dir_x < 0:
            side_dist_x = (pos_x - map_x) * ray_length_x
        else:
            side_dist_x = (map_x + 1.0 - pos_x) * ray_length_x

        if ray_dir_y < 0:
            side_dist_y = (pos_y - map_y) * ray_length_y
        else:
            side_dist_y = (map_y + 1.0 - pos_y) * ray_length_y

        hit = 0
        side = 0
        door_cell = None
        cell = None  # 显式初始化为None

        while hit == 0:
            if side_dist_x < side_dist_y:
                side_dist_x += ray_length_x
                map_x += step_x
                side = 0
            else:
                side_dist_y += ray_length_y
                map_y += step_y
                side = 1

            # 检查位置是否有效
            if not raycaster.game_map.is_valid_position(map_x, map_y):
                hit = 1
                cell = self.boundary_wall  # 使用边界墙
                break

            cell = raycaster.game_map.get_cell(map_x, map_y)

            if isinstance(cell.behavior, DoorBehavior) and (
                    not cell.behavior.door_open or cell.behavior.door_animating):
                door_cell = cell
                hit = 1
            elif cell.is_wall:
                hit = 1

        # 确保cell有值
        if cell is None:
            cell = self.boundary_wall

        # 计算光线距离
        if side == 0:
            perp_dist = (map_x - pos_x + (1 - step_x) / 2) / ray_dir_x
        else:
            perp_dist = (map_y - pos_y + (1 - step_y) / 2) / ray_dir_y

        # 计算墙面位置
        if side == 0:
            wall_x = pos_y + perp_dist * ray_dir_y
        else:
            wall_x = pos_x + perp_dist * ray_dir_x
        wall_x -= math.floor(wall_x)

        return RaycastResult(
            cell=door_cell or cell,
            side=side,
            ray_dir_x=ray_dir_x,
            ray_dir_y=ray_dir_y,
            wall_x=wall_x,
            distance=perp_dist,
            player_dir_x=raycaster.dir_x,
            player_dir_y=raycaster.dir_y
        )

    def _render_minimap(self, stdscr, raycaster, offset_x):
        height, width = stdscr.getmaxyx()
        map_size = 15
        sidebar_width = 30

        try:
            # 顶部标题（显示等级）
            title = f"≡ Lv.{self.player_info.level} 玩家状态 ≡"
            stdscr.addstr(0, offset_x + 2, title.center(sidebar_width - 4))

            # 生命值显示
            health_percent = self.player_info.health / self.player_info.max_health
            health_bar_count = max(1, int(health_percent * 10))
            health_bar = "♥" * health_bar_count
            health_empty = "♡" * (10 - health_bar_count)
            health_line = f"生命: {health_bar}{health_empty} {self.player_info.health}/{self.player_info.max_health}"
            stdscr.addstr(1, offset_x + 2, health_line.ljust(sidebar_width - 4))

            # 技能点显示
            sp_percent = self.player_info.sp / self.player_info.max_sp
            sp_bar_count = max(1, int(sp_percent * 10))
            sp_bar = "✦" * sp_bar_count
            sp_empty = "✧" * (10 - sp_bar_count)
            sp_line = f"技能: {sp_bar}{sp_empty} {self.player_info.sp}/{self.player_info.max_sp}"
            stdscr.addstr(2, offset_x + 2, sp_line.ljust(sidebar_width - 4))

            # 经验值显示
            exp_progress = self.player_info.get_current_level_progress()
            exp_bar_count = int(exp_progress * 10)
            exp_bar = "■" * exp_bar_count
            exp_empty = "□" * (10 - exp_bar_count)

            # 计算当前等级经验值（确保非负）
            current_exp = max(0,
                              self.player_info.exp - self.player_info._exp_required_for_level(self.player_info.level))
            next_level_exp = self.player_info.get_level_up_exp()

            exp_line = f"经验: {exp_bar}{exp_empty} {current_exp}/{next_level_exp}"
            stdscr.addstr(3, offset_x + 2, exp_line.ljust(sidebar_width - 4))

            # 攻击和防御显示
            attack_line = f"攻击: {self.player_info.attack}"
            defense_line = f"防御: {self.player_info.defense}"
            stdscr.addstr(4, offset_x + 2, attack_line.ljust(sidebar_width - 4))
            stdscr.addstr(5, offset_x + 2, defense_line.ljust(sidebar_width - 4))

            # 分隔线
            separator = "─" * (sidebar_width - 4)
            stdscr.addstr(6, offset_x + 2, separator)

            # 小地图显示
            stdscr.addstr(7, offset_x + 2, "小地图:".center(sidebar_width - 4))
            start_row = 8
        except:
            return

        player_x = int(raycaster.pos_x)
        player_y = int(raycaster.pos_y)

        for i in range(map_size):
            row = []
            for j in range(map_size):
                x = j
                y = map_size - 1 - i
                if x == player_x and y == player_y:
                    row.append(self._get_direction_arrow(raycaster.dir_x, raycaster.dir_y))
                else:
                    cell = raycaster.game_map.get_cell(x, y)
                    row.append(cell.get_minimap_char() if cell else " ")
            try:
                # 使用调整后的起始行
                stdscr.addstr(i + start_row, offset_x + 2, "".join(row))
            except:
                pass

    @staticmethod
    def _get_direction_arrow(dir_x, dir_y):
        angle = math.degrees(math.atan2(-dir_y, dir_x)) % 360
        return '↓' if 45 <= angle < 135 else '←' if 135 <= angle < 225 else '↑' if 225 <= angle < 315 else '→'

    def _render_inventory(self, stdscr, game):
        """渲染物品栏界面（支持滚动）"""
        height, width = stdscr.getmaxyx()
        inventory = game.player_info.inventory

        try:
            # 清屏
            stdscr.clear()

            # 绘制上边框
            top_border = "█" * width
            stdscr.addstr(0, 0, top_border)
            stdscr.addstr(1, 0, "█")
            stdscr.addstr(1, width - 1, "█")

            # 绘制标题
            title = "物品栏"
            title_x = (width - len(title)) // 2
            stdscr.addstr(1, title_x, title)

            # 绘制标题下边框
            stdscr.addstr(2, 0, "█" * width)

            # 绘制玩家信息（左侧）
            player_info = [
                f"等级: {game.player_info.level}",
                f"生命: {game.player_info.health}/{game.player_info.max_health}",
                f"技能: {game.player_info.sp}/{game.player_info.max_sp}",
                f"经验: {game.player_info.exp}",
                f"升级需: {game.player_info.get_level_up_exp()}",
                f"进度: {game.player_info.get_current_level_progress() * 100:.1f}%"
            ]

            # 在左侧渲染玩家信息
            for i, line in enumerate(player_info):
                if i < height - 5:
                    stdscr.addstr(3 + i, 1, line)

            # 绘制物品列表（右侧）
            item_start_x = width // 2
            item_start_y = 3

            # 物品栏标题
            stdscr.addstr(item_start_y - 1, item_start_x, "物品列表:")

            # 显示可见物品
            visible_items = inventory.get_visible_items()
            for i, item in enumerate(visible_items):
                display_text = item.get_display_info()
                actual_index = inventory.scroll_offset + i

                # 高亮显示选中的物品
                if actual_index == inventory.selected_index:
                    display_text = f"> {display_text} <"
                    stdscr.addstr(item_start_y + i, item_start_x, display_text, curses.A_REVERSE)
                else:
                    stdscr.addstr(item_start_y + i, item_start_x, f"  {display_text}")

            # 滚动指示器
            if inventory.scroll_offset > 0:
                stdscr.addstr(item_start_y - 1, item_start_x + 15, "↑")
            if inventory.scroll_offset + inventory.visible_slots < len(inventory.items):
                stdscr.addstr(item_start_y + inventory.visible_slots, item_start_x + 15, "↓")

            # 显示选中的物品详情
            selected_item = inventory.get_selected_item()
            if selected_item:
                # 在物品列表下方显示详情
                detail_y = item_start_y + inventory.visible_slots + 2
                detail_lines = selected_item.get_full_info()

                # 确保有足够的空间显示详情
                max_detail_lines = height - detail_y - 2
                if len(detail_lines) > max_detail_lines:
                    detail_lines = detail_lines[:max_detail_lines]

                for i, line in enumerate(detail_lines):
                    stdscr.addstr(detail_y + i, item_start_x, line)

                # 使用提示
                hint_y = detail_y + len(detail_lines) + 1
                if selected_item.item_type == "consumable":
                    stdscr.addstr(hint_y, item_start_x, "按空格键使用此物品")
                elif selected_item.item_type == "equipment":
                    if selected_item.equipped:
                        stdscr.addstr(hint_y, item_start_x, "按空格键卸下此装备")
                    else:
                        stdscr.addstr(hint_y, item_start_x, "按空格键装备此物品")

            # 绘制下边框
            stdscr.addstr(height - 2, 0, "█" * width)

            # 绘制操作提示（左下角）
            hint = "W:上移 S:下移 空格:使用/装备 Q:返回"
            stdscr.addstr(height - 1, 1, hint)

            # 绘制左右边框
            for y in range(3, height - 2):
                stdscr.addch(y, 0, '█')
                stdscr.addch(y, width - 1, '█')

            # 刷新屏幕
            stdscr.refresh()

        except curses.error:
            # 忽略curses错误
            pass


# ====================== 10. 主游戏类 ======================
class RPG:
    def __init__(self):
        # 游戏状态
        self.running = True
        self.inventory_open = False
        self.inventory_transition = None
        self.last_frame_time = time.time()

        # 初始化游戏地图
        self.game_map = GameMap()
        self.game_map.generate_default_map()

        # 初始化光线投射系统
        self.raycaster = Raycaster(self.game_map)

        # 玩家信息
        self.player_info = PlayerInfo()

        # 渲染器
        self.renderer = GameRenderer()

        # 动画系统
        self.animation_renderer = AnimationRenderer()

        # 临时消息
        self.temp_message = None
        self.temp_message_time = 0

        # 注册效果函数
        self._register_effect_functions()

    def _register_effect_functions(self):
        """注册所有效果函数"""

        def teleport_player(game, x, y):
            """传送玩家到指定位置"""
            game.raycaster.pos_x = x + 0.5
            game.raycaster.pos_y = y + 0.5
            return f"传送到位置({x}, {y})"

        def level_up_player(game, levels=1):
            """提升玩家等级"""
            game.player_info.change_level(levels)
            return f"等级提升 {levels} 级"

        # 注册函数
        ItemFactory.register_function("teleport", teleport_player)
        ItemFactory.register_function("level_up", level_up_player)

    def run(self):
        """运行游戏主循环"""
        curses.wrapper(self._main_loop)

    def _main_loop(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(1)
        while self.running:
            delta_time = time.time() - self.last_frame_time
            self.last_frame_time = time.time()

            # 更新过渡动画状态
            if self.inventory_transition:
                self.inventory_transition.update(delta_time)
                if self.inventory_transition.completed:
                    self.inventory_transition = None

            # 处理输入
            key = stdscr.getch()
            if key == ord('q'):
                self.running = False
            elif key == ord('i') and not self.inventory_transition:
                # 切换物品栏状态
                self.inventory_transition = InventoryTransitionAnimation(
                    is_entering=not self.inventory_open
                )
                self.inventory_open = not self.inventory_open
            elif self.inventory_open:
                # 物品栏界面专用输入处理
                inventory = self.player_info.inventory

                if key == ord('w'):
                    inventory.move_selection("up")
                elif key == ord('s'):
                    inventory.move_selection("down")
                elif key == ord(' '):
                    selected_item = inventory.get_selected_item()
                    if selected_item:
                        if selected_item.item_type == "consumable":
                            # 使用消耗品
                            result = self._use_consumable(selected_item)
                            self._show_temp_message(stdscr, result)
                        elif selected_item.item_type == "equipment":
                            # 装备/卸下装备
                            if selected_item.equipped:
                                result = inventory.unequip_item(selected_item, self)
                            else:
                                result = inventory.equip_item(selected_item, self)
                            self._show_temp_message(stdscr, result)
            elif not self.inventory_transition:
                # 游戏界面输入处理
                if key == ord('w'):
                    self.raycaster.move(forward=True)  # 向前移动
                elif key == ord('s'):
                    self.raycaster.move(forward=False)  # 向后移动
                elif key == ord('a'):
                    self.raycaster.rotate(clockwise=False)  # 向左转
                elif key == ord('d'):
                    self.raycaster.rotate(clockwise=True)  # 向右转
                elif key == ord(' '):  # 空格键交互
                    front_cell = self.raycaster.get_front_cell()
                    if front_cell and front_cell.behavior:
                        # 获取玩家前方位置
                        front_x = int(self.raycaster.pos_x + self.raycaster.dir_x * 0.7)
                        front_y = int(self.raycaster.pos_y + self.raycaster.dir_y * 0.7)
                        front_cell.behavior.on_interact(self, front_x, front_y)

            # 更新旋转动画
            self.raycaster.update_rotation()

            # 更新地图行为
            self.game_map.accept_visitor(AnimationUpdater(delta_time))

            # 渲染游戏
            if not self.inventory_open:
                self.renderer.render_game(stdscr, self)

            # 渲染物品栏界面（覆盖整个画面）
            if self.inventory_open:
                self.renderer._render_inventory(stdscr, self)

            # 渲染过渡动画（覆盖在最上层）
            if self.inventory_transition:
                self.inventory_transition.render(stdscr, self)

            # 设置超时
            stdscr.timeout(50)

    def _use_consumable(self, item: Item) -> str:
        """使用消耗品"""
        player = self.player_info
        results = []

        # 应用效果
        for effect in item.definition.effects:
            if effect.effect_type == "function":
                # 执行函数效果
                func = ItemFactory._function_registry.get(effect.value)
                if func:
                    try:
                        result = func(self, *effect.args, **effect.kwargs)
                        results.append(result)
                    except Exception as e:
                        results.append(f"效果执行失败: {str(e)}")
                else:
                    results.append(f"未知效果函数: {effect.value}")
            else:
                # 数值效果
                if effect.effect_type == "health":
                    player.heal(effect.value)
                elif effect.effect_type == "sp":
                    player.restore_sp(effect.value)
                elif effect.effect_type == "exp":
                    player.add_exp(effect.value)
                elif effect.effect_type == "attack":
                    player.attack += effect.value
                elif effect.effect_type == "defense":
                    player.defense += effect.value
                elif effect.effect_type == "max_health":
                    player.max_health += effect.value
                    player.health = min(player.health, player.max_health)
                elif effect.effect_type == "max_sp":
                    player.max_sp += effect.value
                    player.sp = min(player.sp, player.max_sp)

        # 减少数量（如果是有限使用物品）
        if item.usage_type == "single":
            # 减少数量或移除物品
            if item.count > 1:
                item.count -= 1
            else:
                # 移除物品
                index = self.player_info.inventory.items.index(item)
                self.player_info.inventory.remove_item(index)

        # 返回使用结果
        effect_names = {
            "health": "生命值",
            "sp": "技能值",
            "exp": "经验值",
            "max_health": "最大生命值",
            "max_sp": "最大技能值",
            "attack": "攻击力",
            "defense": "防御力"
        }
        effects = ", ".join(
            f"{effect_names.get(e.effect_type, e.effect_type)}+{e.value}"
            for e in item.definition.effects
        )

        return f"使用了 {item.name}: {effects}"

    def _show_temp_message(self, stdscr, message: str, duration: float = 1.5):
        """显示临时消息"""
        height, width = stdscr.getmaxyx()
        try:
            # 在屏幕底部显示消息
            msg_y = height - 3
            msg_x = max(0, (width - len(message)) // 2)

            # 保存原始内容
            original_line = stdscr.instr(msg_y, 0, width - 1).decode('utf-8', 'ignore').rstrip()

            # 显示消息
            stdscr.addstr(msg_y, msg_x, message)
            stdscr.refresh()

            # 短暂延迟
            time.sleep(duration)

            # 恢复原始内容
            stdscr.addstr(msg_y, 0, original_line)
            stdscr.refresh()
        except:
            pass


if __name__ == "__main__":
    RPG().run()
