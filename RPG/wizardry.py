from abc import ABC, abstractmethod
import curses
import math
import time
import sys


# ====================== 1. 参数类 ======================
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


# ====================== 2. 行为策略 ======================
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
            return True
        return False


# ====================== 3. 渲染组件 ======================
class CellRenderer(ABC):
    """单元格渲染组件基类"""

    @abstractmethod
    def render_3d(self, context: RenderContext) -> str: pass

    @abstractmethod
    def get_minimap_char(self) -> str: pass


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


class InteractiveFloorRenderer(CellRenderer):
    """互动地板渲染组件实现"""

    def __init__(self, behavior):
        self.behavior = behavior

    def render_3d(self, context: RenderContext) -> str: return " "

    def get_minimap_char(self): return "*" if self.behavior.triggered else "."


class FloorRenderer(CellRenderer):
    """普通地板渲染组件实现"""

    def render_3d(self, context: RenderContext) -> str: return " "

    def get_minimap_char(self): return "."


# ====================== 4. 访问者模式 ======================
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


# ====================== 5. 状态信息提供者 ======================
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


# ====================== 6. 地图与单元格 ======================
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


# ====================== 7. 光线投射器 ======================
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


# ====================== 8. 游戏渲染器 ======================
class GameRenderer:
    """游戏渲染器"""

    def __init__(self):
        self.status_manager = StatusInfoManager()

    def render_game(self, stdscr, game):
        height, width = stdscr.getmaxyx()
        stdscr.clear()

        # 全屏闪烁检测
        flash_cell = None
        for row in game.game_map.grid:
            for cell in row:
                if cell.behavior and isinstance(cell.behavior, InteractiveFloorBehavior) and \
                        time.time() - cell.behavior.trigger_time < 0.5:
                    flash_cell = cell
                    break
            if flash_cell:
                break

        # 检查是否需要全屏闪烁
        if flash_cell and int((time.time() - flash_cell.behavior.trigger_time) * 10) % 2 == 0:
            for y in range(height):
                try:
                    stdscr.addstr(y, 0, "#" * (width - 1))
                except:
                    pass
            return

        # 正常渲染流程
        render_height = height - 2
        render_width = width - 20

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
        # 玩家当前位置
        pos_x, pos_y = raycaster.pos_x, raycaster.pos_y

        # 玩家所在网格位置
        map_x, map_y = int(pos_x), int(pos_y)

        # 光线方向向量的长度（用于防止除零错误）
        ray_length_x = abs(1 / ray_dir_x) if ray_dir_x != 0 else float('inf')
        ray_length_y = abs(1 / ray_dir_y) if ray_dir_y != 0 else float('inf')

        # 步进方向
        step_x = 1 if ray_dir_x >= 0 else -1
        step_y = 1 if ray_dir_y >= 0 else -1

        # 到下一个网格边界的初始距离
        if ray_dir_x < 0:
            side_dist_x = (pos_x - map_x) * ray_length_x
        else:
            side_dist_x = (map_x + 1.0 - pos_x) * ray_length_x

        if ray_dir_y < 0:
            side_dist_y = (pos_y - map_y) * ray_length_y
        else:
            side_dist_y = (map_y + 1.0 - pos_y) * ray_length_y

        # 光线投射循环
        hit = 0
        side = 0
        door_cell = None

        while hit == 0:
            # 跳转到下一个网格边界
            if side_dist_x < side_dist_y:
                side_dist_x += ray_length_x
                map_x += step_x
                side = 0  # 垂直面
            else:
                side_dist_y += ray_length_y
                map_y += step_y
                side = 1  # 水平面

            # 检查是否超出地图边界
            if not raycaster.game_map.is_valid_position(map_x, map_y):
                hit = 1
                break

            # 获取当前网格的单元格
            cell = raycaster.game_map.get_cell(map_x, map_y)

            # 检查是否是门（关闭或动画中）
            if isinstance(cell.behavior, DoorBehavior) and (
                    not cell.behavior.door_open or cell.behavior.door_animating):
                door_cell = cell
                hit = 1
            # 检查是否是墙
            elif cell.is_wall:
                hit = 1

        # 计算光线距离
        if side == 0:
            perp_dist = (map_x - pos_x + (1 - step_x) / 2) / ray_dir_x
        else:
            perp_dist = (map_y - pos_y + (1 - step_y) / 2) / ray_dir_y

        # 计算墙面位置（用于纹理渲染）
        if side == 0:
            wall_x = pos_y + perp_dist * ray_dir_y
        else:
            wall_x = pos_x + perp_dist * ray_dir_x
        wall_x -= math.floor(wall_x)

        # 返回光线投射结果（包含玩家方向信息）
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
        player_x = int(raycaster.pos_x)
        player_y = int(raycaster.pos_y)

        try:
            stdscr.addstr(0, offset_x + 2, "小地图:")
        except:
            return

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
                stdscr.addstr(i + 1, offset_x + 2, "".join(row))
            except:
                pass

    @staticmethod
    def _get_direction_arrow(dir_x, dir_y):
        angle = math.degrees(math.atan2(-dir_y, dir_x)) % 360
        return '↓' if 45 <= angle < 135 else '←' if 135 <= angle < 225 else '↑' if 225 <= angle < 315 else '→'


# ====================== 9. 状态信息管理器 ======================
class StatusInfoManager:
    """状态信息管理器"""

    def __init__(self):
        self.providers = [DoorStatusProvider(), FloorStatusProvider()]

    def get_status_info(self, game) -> str:
        x, y = int(game.raycaster.pos_x), int(game.raycaster.pos_y)
        return "".join(provider.get_status_info(game, x, y) for provider in self.providers)


# ====================== 10. 主游戏类 ======================
class RPG:
    """主游戏类"""

    def __init__(self):
        self.game_map = GameMap()
        self.game_map.generate_default_map()
        self.raycaster = Raycaster(self.game_map)
        self.renderer = GameRenderer()
        self.last_frame_time = time.time()

    def run(self):
        curses.wrapper(self._main_loop)

    def _main_loop(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(1)
        while True:
            delta_time = time.time() - self.last_frame_time
            self.last_frame_time = time.time()

            self.raycaster.update_rotation()
            self.game_map.accept_visitor(AnimationUpdater(delta_time))

            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('w'):
                self.raycaster.move()
                self.game_map.accept_visitor(StepHandler(self, int(self.raycaster.pos_x), int(self.raycaster.pos_y)))
            elif key == ord('s'):
                self.raycaster.move(False)
            elif key == ord('a'):
                self.raycaster.rotate(False)
            elif key == ord('d'):
                self.raycaster.rotate()
            elif key == ord(' '):
                front_cell = self.raycaster.get_front_cell()
                if front_cell and front_cell.behavior:
                    front_cell.behavior.on_interact(self, int(self.raycaster.pos_x), int(self.raycaster.pos_y))

            self.renderer.render_game(stdscr, self)
            stdscr.timeout(20 if self.raycaster.rotating else 100)


if __name__ == "__main__":
    RPG().run()
