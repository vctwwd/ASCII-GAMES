import curses
import math
import time


class MapCell:
    """基础地图单元格类，处理墙壁和地板"""
    TEXTURE_LIB = {
        "outer_wall_vertical": "|",
        "outer_wall_horizontal": "-",
        "inner_wall_vertical": "|",
        "inner_wall_horizontal": "-",
        "floor": " ",
        "window": "[]",
        "secret": "?",
    }

    def __init__(self, is_wall=False, texture_id="floor"):
        self.is_wall = is_wall
        self.texture_id = texture_id

    def get_texture_char(self, side, ray_dir_x, ray_dir_y, wall_x=None, distance=None):
        """获取单元格的纹理字符"""
        if side == 0:
            angle = math.degrees(math.atan2(ray_dir_y, ray_dir_x))
        else:
            angle = math.degrees(math.atan2(ray_dir_x, ray_dir_y))

        angle = (angle + 360) % 360

        if 45 <= angle < 135 or 225 <= angle < 315:
            direction = "vertical"
        else:
            direction = "horizontal"

        texture_key = f"{self.texture_id}_{direction}"
        return self.TEXTURE_LIB.get(texture_key, "#")

    def __str__(self):
        """字符串表示，用于小地图"""
        return "#" if self.is_wall else "."


class DoorCell(MapCell):
    """门单元格类，继承自MapCell并添加门特有功能"""

    def __init__(self, texture_id="door"):
        super().__init__(is_wall=True, texture_id=texture_id)
        self.is_door = True
        self.door_open = False
        self.door_animating = False
        self.door_animation_type = None
        self.door_animation_progress = 0.0
        self.door_direction = "horizontal"

    def get_texture_char(self, side, ray_dir_x, ray_dir_y, wall_x=None, distance=None):
        """获取门的纹理字符，处理门框和门板"""
        # 确定门的方向
        if side == 0:
            angle = math.degrees(math.atan2(ray_dir_y, ray_dir_x))
        else:
            angle = math.degrees(math.atan2(ray_dir_x, ray_dir_y))

        angle = (angle + 360) % 360

        if 45 <= angle < 135 or 225 <= angle < 315:
            direction = "vertical"
            self.door_direction = "vertical"
        else:
            direction = "horizontal"
            self.door_direction = "horizontal"

        texture_key = f"{self.texture_id}_{direction}"
        base_char = self.TEXTURE_LIB.get(texture_key, "#")

        # 门框渲染逻辑
        frame_thickness = 0.15
        if distance is not None and distance < 1.5:
            frame_thickness = 0.25

        # 始终显示门框（无论门是开是关）
        if wall_x is not None:
            if wall_x < frame_thickness or wall_x > 1 - frame_thickness:
                return "▐"  # 门框

        # 门板渲染逻辑
        if self.door_animating:
            # 动画中的门
            if wall_x is not None:
                if self.door_animation_type == "opening":
                    # 开门动画：门扇从中间向两侧打开
                    threshold = 0.5 * self.door_animation_progress
                    if wall_x < 0.5 - threshold or wall_x > 0.5 + threshold:
                        return base_char  # 门板
                    return " "  # 打开的空间
                elif self.door_animation_type == "closing":
                    # 关门动画：门扇从两侧向中间合拢
                    threshold = 0.5 * (1 - self.door_animation_progress)
                    if wall_x < 0.5 - threshold or wall_x > 0.5 + threshold:
                        return base_char  # 门板
                    return " "  # 关闭中的空间
            return base_char

        # 非动画状态的门
        if self.door_open:
            # 打开的门 - 只显示门框，中间是空白
            return " "  # 打开的空间
        else:
            # 关闭的门 - 显示完整门板
            return base_char  # 门板

    def toggle_door(self):
        """切换门的状态（开/关）"""
        if not self.door_animating:
            self.door_animating = True
            self.door_animation_progress = 0.0
            if self.door_open:
                self.door_animation_type = "closing"
            else:
                self.door_animation_type = "opening"

    def update_door_animation(self, delta_time):
        """更新门动画状态"""
        if self.door_animating:
            self.door_animation_progress += delta_time * 2.0
            if self.door_animation_progress >= 1.0:
                self.door_animating = False
                self.door_open = not self.door_open
                self.door_animation_type = None

    def __str__(self):
        """字符串表示，用于小地图"""
        return " " if self.door_open else "+"


class InteractiveFloorCell(MapCell):
    """互动地板单元格类，继承自MapCell"""

    def __init__(self, texture_id="floor", effect_type=None, can_retrigger=False):
        """
        初始化互动地板
        :param effect_type: 效果类型（预留扩展）
        :param can_retrigger: 是否可以重复触发
        """
        super().__init__(is_wall=False, texture_id=texture_id)
        self.effect_type = effect_type
        self.can_retrigger = can_retrigger
        self.triggered = False  # 是否已触发
        self.trigger_time = 0  # 触发时间（用于动画）

    def trigger(self):
        """触发地板效果"""
        if not self.triggered or self.can_retrigger:
            self.triggered = True
            self.trigger_time = time.time()
            # 这里可以添加根据effect_type执行不同效果的逻辑
            # 例如：传送、伤害、机关触发等
            return True
        return False

    def get_texture_char(self, side, ray_dir_x, ray_dir_y, wall_x=None, distance=None):
        """获取纹理字符，触发后显示为'.'"""
        if self.triggered:
            # 添加简单的闪烁动画效果
            elapsed = time.time() - self.trigger_time
            if elapsed < 0.5 and int(elapsed * 10) % 2 == 0:
                return "."
            return " "  # 半秒后恢复为普通地板
        return super().get_texture_char(side, ray_dir_x, ray_dir_y, wall_x, distance)

    def __str__(self):
        """小地图显示，触发后显示为'*'"""
        return "*" if self.triggered else "."


class GameMap:
    """游戏地图类，管理所有单元格"""

    def __init__(self, width=10, height=10):
        self.width = width
        self.height = height
        self.grid = [[MapCell() for _ in range(width)] for _ in range(height)]

    def generate_default_map(self):
        """生成默认地图布局"""
        # 创建外边界墙
        for i in range(self.height):
            self.grid[i][0] = MapCell(is_wall=True, texture_id="outer_wall")
            self.grid[i][self.width - 1] = MapCell(is_wall=True, texture_id="outer_wall")
        for j in range(self.width):
            self.grid[0][j] = MapCell(is_wall=True, texture_id="outer_wall")
            self.grid[self.height - 1][j] = MapCell(is_wall=True, texture_id="outer_wall")

        # 创建中间墙和门
        wall_row = self.height // 2
        for j in range(3, 8):
            if j == 5:
                self.grid[wall_row][j] = DoorCell(texture_id="door")
            else:
                self.grid[wall_row][j] = MapCell(is_wall=True, texture_id="inner_wall")

        # 添加互动地板示例
        self.grid[3][3] = InteractiveFloorCell(effect_type="sample", can_retrigger=True)
        self.grid[7][7] = InteractiveFloorCell(effect_type="sample", can_retrigger=False)

    def is_valid_position(self, x, y):
        """检查坐标是否在地图范围内"""
        return 0 <= x < self.height and 0 <= y < self.width

    def is_wall(self, x, y):
        """检查指定位置是否是墙壁（包括关闭的门）"""
        if not self.is_valid_position(x, y):
            return True
        cell = self.grid[x][y]
        if hasattr(cell, 'is_door') and cell.is_door and cell.door_open:
            return False
        return cell.is_wall

    def get_cell(self, x, y):
        """获取指定位置的单元格"""
        if self.is_valid_position(x, y):
            return self.grid[x][y]
        return None

    def update_animations(self, delta_time):
        """更新所有动画状态"""
        for i in range(self.height):
            for j in range(self.width):
                cell = self.grid[i][j]
                if hasattr(cell, 'is_door') and cell.is_door and cell.door_animating:
                    cell.update_door_animation(delta_time)


class Raycaster:
    """光线投射类，处理玩家视角和移动"""

    def __init__(self, game_map):
        self.game_map = game_map
        self.pos_x = 1.5
        self.pos_y = 1.5
        self.dir_x = 1
        self.dir_y = 0
        self.plane_x = 0
        self.plane_y = -0.66
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
        """旋转玩家视角"""
        rot = self.rotate_angle * (-1 if clockwise else 1)
        self.target_dir_x = self.dir_x * math.cos(rot) - self.dir_y * math.sin(rot)
        self.target_dir_y = self.dir_x * math.sin(rot) + self.dir_y * math.cos(rot)
        self.target_plane_x = self.plane_x * math.cos(rot) - self.plane_y * math.sin(rot)
        self.target_plane_y = self.plane_x * math.sin(rot) + self.plane_y * math.cos(rot)

        self.rotating = True
        self.rotation_progress = 0.0

    def update_rotation(self):
        """更新旋转动画状态"""
        if not self.rotating:
            return

        self.rotation_progress += self.rotation_speed

        if self.rotation_progress >= 1.0:
            self.dir_x = self.target_dir_x
            self.dir_y = self.target_dir_y
            self.plane_x = self.target_plane_x
            self.plane_y = self.target_plane_y
            self.rotating = False
            return

        self.dir_x = self.dir_x * (1 - self.rotation_progress) + self.target_dir_x * self.rotation_progress
        self.dir_y = self.dir_y * (1 - self.rotation_progress) + self.target_dir_y * self.rotation_progress
        self.plane_x = self.plane_x * (1 - self.rotation_progress) + self.target_plane_x * self.rotation_progress
        self.plane_y = self.plane_y * (1 - self.rotation_progress) + self.target_plane_y * self.rotation_progress

    def turn_around(self):
        """玩家向后转"""
        self.dir_x = -self.dir_x
        self.dir_y = -self.dir_y
        self.plane_x = -self.plane_x
        self.plane_y = -self.plane_y
        self.target_dir_x = self.dir_x
        self.target_dir_y = self.dir_y
        self.target_plane_x = self.plane_x
        self.target_plane_y = self.plane_y

    def move(self, forward=True):
        """移动玩家位置"""
        move = self.move_distance * (1 if forward else -1)
        new_x = self.pos_x + self.dir_x * move
        new_y = self.pos_y + self.dir_y * move
        target_x = int(new_x)
        target_y = int(new_y)

        if self.game_map.is_valid_position(target_x, target_y):
            if not self.game_map.is_wall(target_x, target_y):
                self.pos_x = target_x + 0.5
                self.pos_y = target_y + 0.5

                # 检测并触发互动地板
                cell = self.game_map.get_cell(target_x, target_y)
                if isinstance(cell, InteractiveFloorCell):
                    cell.trigger()

    def get_front_cell(self):
        """获取玩家面前的单元格"""
        front_x = int(self.pos_x + self.dir_x * 0.7)
        front_y = int(self.pos_y + self.dir_y * 0.7)
        if self.game_map.is_valid_position(front_x, front_y):
            return self.game_map.get_cell(front_x, front_y)
        return None


class GameRenderer:
    """游戏渲染类，负责所有画面绘制工作"""

    @staticmethod
    def render_game(stdscr, raycaster):
        """主渲染方法"""
        height, width = stdscr.getmaxyx()
        stdscr.clear()
        render_height = height - 2
        render_width = width - 20

        # 渲染3D视图
        GameRenderer._render_3d_view(stdscr, raycaster, render_width, render_height)

        # 渲染状态栏
        GameRenderer._render_status_bar(stdscr, raycaster, height, width)

        # 渲染小地图
        GameRenderer._render_minimap(stdscr, raycaster, render_width)

    @staticmethod
    def _render_3d_view(stdscr, raycaster, render_width, render_height):
        """渲染3D视角画面"""
        for x in range(render_width):
            ray_dir_x, ray_dir_y = GameRenderer._calculate_ray_direction(
                raycaster, x, render_width)

            hit_info = GameRenderer._cast_ray(raycaster, ray_dir_x, ray_dir_y)
            # 关键修复：添加光线方向参数
            hit_info['ray_dir_x'] = ray_dir_x
            hit_info['ray_dir_y'] = ray_dir_y

            if hit_info['door_cell']:
                GameRenderer._render_door(stdscr, raycaster, x, hit_info, render_height)
            else:
                GameRenderer._render_wall(stdscr, raycaster, x, hit_info, render_height)

    @staticmethod
    def _calculate_ray_direction(raycaster, x, render_width):
        """计算单条光线的方向"""
        camera_x = 2 * x / render_width - 1
        return (
            raycaster.dir_x + raycaster.plane_x * camera_x,
            raycaster.dir_y + raycaster.plane_y * camera_x
        )

    @staticmethod
    def _cast_ray(raycaster, ray_dir_x, ray_dir_y):
        """执行单条光线投射，返回碰撞信息"""
        map_x, map_y = int(raycaster.pos_x), int(raycaster.pos_y)
        step_x, step_y, side_dist_x, side_dist_y = GameRenderer._init_ray_step(
            raycaster, ray_dir_x, ray_dir_y)

        hit_info = {
            'hit': 0,
            'side': 0,
            'door_cell': None,
            'door_side': 0,
            'door_wall_x': 0,
            'door_perp_dist': 0,
            'final_cell': None,
            'ray_dir_x': ray_dir_x,  # 存储光线方向
            'ray_dir_y': ray_dir_y  # 存储光线方向
        }

        # 临时变量用于光线步进
        current_map_x = map_x
        current_map_y = map_y
        current_side_dist_x = side_dist_x
        current_side_dist_y = side_dist_y

        while hit_info['hit'] == 0:
            # 推进光线
            if current_side_dist_x < current_side_dist_y:
                current_side_dist_x += abs(1 / ray_dir_x) if ray_dir_x != 0 else 1e30
                current_map_x += step_x
                hit_info['side'] = 0
            else:
                current_side_dist_y += abs(1 / ray_dir_y) if ray_dir_y != 0 else 1e30
                current_map_y += step_y
                hit_info['side'] = 1

            # 检查是否超出地图边界
            if not raycaster.game_map.is_valid_position(current_map_x, current_map_y):
                hit_info['hit'] = 1
                break

            # 获取当前单元格
            cell = raycaster.game_map.get_cell(current_map_x, current_map_y)
            hit_info['final_cell'] = cell

            # 检查是否是门
            if hasattr(cell, 'is_door') and cell.is_door:
                # 计算门的位置信息
                if hit_info['side'] == 0:
                    perp_dist = (current_map_x - raycaster.pos_x + (1 - step_x) / 2) / ray_dir_x
                else:
                    perp_dist = (current_map_y - raycaster.pos_y + (1 - step_y) / 2) / ray_dir_y

                if hit_info['side'] == 0:
                    wall_x = raycaster.pos_y + perp_dist * ray_dir_y
                else:
                    wall_x = raycaster.pos_x + perp_dist * ray_dir_x
                wall_x -= math.floor(wall_x)

                hit_info['door_cell'] = cell
                hit_info['door_side'] = hit_info['side']
                hit_info['door_wall_x'] = wall_x
                hit_info['door_perp_dist'] = perp_dist

                # 如果是关闭的门，停止光线投射
                if not cell.door_open and not cell.door_animating:
                    hit_info['hit'] = 1
                    break
                # 否则继续投射
                else:
                    continue

            # 检查是否是墙壁
            if cell and cell.is_wall:
                hit_info['hit'] = 1
                break

        # 计算最终墙壁距离
        if hit_info['side'] == 0:
            perp_wall_dist = (current_map_x - raycaster.pos_x + (1 - step_x) / 2) / ray_dir_x
        else:
            perp_wall_dist = (current_map_y - raycaster.pos_y + (1 - step_y) / 2) / ray_dir_y

        hit_info['perp_wall_dist'] = perp_wall_dist
        return hit_info

    @staticmethod
    def _init_ray_step(raycaster, ray_dir_x, ray_dir_y):
        """初始化光线步进参数"""
        delta_dist_x = abs(1 / ray_dir_x) if ray_dir_x != 0 else 1e30
        delta_dist_y = abs(1 / ray_dir_y) if ray_dir_y != 0 else 1e30

        step_x = 1 if ray_dir_x >= 0 else -1
        step_y = 1 if ray_dir_y >= 0 else -1

        side_dist_x = (
            (raycaster.pos_x - int(raycaster.pos_x)) * delta_dist_x
            if ray_dir_x < 0
            else (int(raycaster.pos_x) + 1.0 - raycaster.pos_x) * delta_dist_x
        )
        side_dist_y = (
            (raycaster.pos_y - int(raycaster.pos_y)) * delta_dist_y
            if ray_dir_y < 0
            else (int(raycaster.pos_y) + 1.0 - raycaster.pos_y) * delta_dist_y
        )

        return step_x, step_y, side_dist_x, side_dist_y

    @staticmethod
    def _render_door(stdscr, raycaster, x, hit_info, render_height):
        """渲染门对象"""
        door_cell = hit_info['door_cell']
        door_perp_dist = max(hit_info['door_perp_dist'], 0.1)

        door_height = int(render_height / door_perp_dist)
        max_wall_height = int(render_height * 0.9)
        door_height = min(door_height, max_wall_height)

        door_draw_start = max(1, render_height // 2 - door_height // 2)
        door_draw_end = min(render_height, render_height // 2 + door_height // 2)

        # 关键修复：传递正确的光线方向参数
        door_char = door_cell.get_texture_char(
            hit_info['door_side'],
            hit_info['ray_dir_x'],
            hit_info['ray_dir_y'],
            hit_info['door_wall_x'],
            door_perp_dist
        )

        for y in range(door_draw_start, door_draw_end + 1):
            if 0 <= y < stdscr.getmaxyx()[0] and 0 <= x < stdscr.getmaxyx()[1]:
                try:
                    stdscr.addch(y, x, door_char)
                except:
                    pass

    @staticmethod
    def _render_wall(stdscr, raycaster, x, hit_info, render_height):
        """渲染普通墙壁"""
        perp_wall_dist = max(hit_info['perp_wall_dist'], 0.1)
        wall_height = int(render_height / perp_wall_dist)
        wall_height = min(wall_height, int(render_height * 0.9))

        draw_start = max(1, render_height // 2 - wall_height // 2)
        draw_end = min(render_height, render_height // 2 + wall_height // 2)

        # 计算墙面X坐标
        if hit_info['side'] == 0:
            wall_x = raycaster.pos_y + perp_wall_dist * hit_info['ray_dir_y']
        else:
            wall_x = raycaster.pos_x + perp_wall_dist * hit_info['ray_dir_x']
        wall_x -= math.floor(wall_x)

        if hit_info['final_cell']:
            # 关键修复：传递正确的光线方向参数
            wall_char = hit_info['final_cell'].get_texture_char(
                hit_info['side'],
                hit_info['ray_dir_x'],
                hit_info['ray_dir_y'],
                wall_x,
                perp_wall_dist
            )
        else:
            wall_char = "|" if hit_info['side'] == 0 else "-"

        # 防黑屏保护
        if wall_char == " ":
            wall_char = "|" if hit_info['side'] == 0 else "-"

        # 渲染墙壁列
        for y in range(draw_start, draw_end + 1):
            if 0 <= y < stdscr.getmaxyx()[0] and 0 <= x < stdscr.getmaxyx()[1]:
                try:
                    stdscr.addch(y, x, wall_char)
                except:
                    pass

    @staticmethod
    def _render_status_bar(stdscr, raycaster, height, width):
        """渲染状态栏"""
        # 方向计算
        angle = math.degrees(math.atan2(-raycaster.dir_y, raycaster.dir_x))
        direction = "北" if 45 <= angle < 135 else \
            "西" if 135 <= angle < 225 else \
                "南" if 225 <= angle < 315 else "东"

        # 位置信息
        grid_x, grid_y = int(raycaster.pos_x), int(raycaster.pos_y)
        status_line1 = f"位置: (行:{grid_x}, 列:{grid_y}) 方向: {direction}"

        # 门状态信息
        status_line2 = GameRenderer._get_door_status(raycaster)

        # 添加互动地板状态信息
        current_cell = raycaster.game_map.get_cell(int(raycaster.pos_x), int(raycaster.pos_y))
        if isinstance(current_cell, InteractiveFloorCell):
            status_line2 += " [互动地板]" + ("已触发" if current_cell.triggered else "未触发")

        # 控制提示
        controls = "W:前进 A:左转 D:右转 S:向后转 空格:开门 Q:退出"

        try:
            # 顶部控制提示
            stdscr.addstr(0, 0, controls[:width - 1])

            # 底部状态栏
            stdscr.addstr(height - 2, 0, status_line1[:width - 1])
            stdscr.addstr(height - 1, 0, status_line2[:width - 1])
        except curses.error:
            # 忽略窗口大小变化导致的渲染错误
            pass

    @staticmethod
    def _get_door_status(raycaster):
        """获取门状态描述"""
        front_cell = raycaster.get_front_cell()
        if not front_cell:
            return " "

        if not hasattr(front_cell, 'is_door') or not front_cell.is_door:
            return " [面前无门]"

        if front_cell.door_animating:
            if front_cell.door_animation_type == "opening":
                return " [开门中]"
            elif front_cell.door_animation_type == "closing":
                return " [关门中]"
            return " [门状态变化中]"

        return " [门已开]" if front_cell.door_open else " [门前]"

    @staticmethod
    def _render_minimap(stdscr, raycaster, render_width):
        """渲染小地图"""
        height, width = stdscr.getmaxyx()
        map_width = min(raycaster.game_map.width, 15)
        map_height = min(raycaster.game_map.height, 15)
        grid_x, grid_y = int(raycaster.pos_x), int(raycaster.pos_y)

        try:
            # 小地图标题
            stdscr.addstr(0, render_width + 2, "小地图:")
        except curses.error:
            return

        # 获取方向箭头
        arrow = GameRenderer.get_direction_arrow(raycaster.dir_x, raycaster.dir_y)

        # 渲染小地图网格
        for i in range(map_height):
            row_str = ""
            for j in range(map_width):
                # 计算小地图坐标（旋转90度）
                map_x = j
                map_y = map_height - 1 - i

                # 检查是否是玩家位置
                if map_x == grid_x and map_y == grid_y:
                    row_str += arrow
                else:
                    # 获取地图单元格
                    if raycaster.game_map.is_valid_position(map_x, map_y):
                        cell = raycaster.game_map.get_cell(map_x, map_y)
                        row_str += str(cell)
                    else:
                        row_str += " "

            # 确保行号在屏幕范围内
            if i + 1 < height:
                try:
                    stdscr.addstr(i + 1, render_width + 2, row_str)
                except curses.error:
                    # 忽略超出屏幕的渲染
                    pass

    @staticmethod
    def get_direction_arrow(dir_x, dir_y):
        """获取方向箭头符号"""
        angle = math.degrees(math.atan2(-dir_y, dir_x))
        angle = (angle + 360) % 360

        if 45 <= angle < 135:
            return '↓'  # 北
        elif 135 <= angle < 225:
            return '←'  # 西
        elif 225 <= angle < 315:
            return '↑'  # 南
        else:
            return '→'  # 东


class RPG:
    """主游戏类"""

    def __init__(self):
        self.game_map = GameMap(10, 10)
        self.game_map.generate_default_map()
        self.raycaster = Raycaster(self.game_map)
        self.last_frame_time = time.time()

    def run(self):
        """运行游戏主循环"""
        curses.wrapper(self.main)

    def main(self, stdscr):
        """游戏主函数"""
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.timeout(100)

        while True:
            current_time = time.time()
            delta_time = current_time - self.last_frame_time
            self.last_frame_time = current_time

            # 更新旋转和动画状态
            self.raycaster.update_rotation()
            self.game_map.update_animations(delta_time)

            # 处理键盘输入
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('w'):
                self.raycaster.move(forward=True)
            elif key == ord('s'):
                self.raycaster.turn_around()
            elif key == ord('a'):
                self.raycaster.rotate(clockwise=False)
            elif key == ord('d'):
                self.raycaster.rotate(clockwise=True)
            elif key == ord(' '):  # 空格键开门
                front_cell = self.raycaster.get_front_cell()
                if front_cell and hasattr(front_cell, 'is_door') and front_cell.is_door:
                    front_cell.toggle_door()

            # 渲染游戏
            GameRenderer.render_game(stdscr, self.raycaster)

            # 动画期间的延迟优化
            if self.raycaster.rotating or any(
                    hasattr(cell, 'door_animating') and cell.door_animating
                    for row in self.game_map.grid for cell in row
            ):
                stdscr.timeout(20)
            else:
                stdscr.timeout(100)


if __name__ == "__main__":
    game = RPG()
    game.run()
