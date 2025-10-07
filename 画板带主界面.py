import sys
import os
import winreg
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QSlider, QColorDialog,
                             QFrame, QMessageBox, QToolButton, QFileDialog,
                             QSystemTrayIcon, QMenu, QAction, QCheckBox)
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QCursor, QMouseEvent, QIcon
from threading import Thread
from pynput import mouse, keyboard


class DrawingOverlay(QMainWindow):
    trigger_toggle_signal = pyqtSignal()  # 添加信号

    def __init__(self, pen_color=QColor(255, 0, 0), pen_width=5):
        super().__init__()
        self.drawing_enabled = False
        self.ctrl_pressed = False

        # 接收默认颜色和笔粗细
        self.pen_color = pen_color
        self.pen_width = pen_width

        self.trigger_toggle_signal.connect(self.toggle_drawing_mode)
        Thread(target=self.start_global_hotkey_listener, daemon=True).start()

        # 绘画相关变量
        self.drawing = False
        self.last_point = QPoint()
        self.drawing_mode = "pen"  # "pen" 或 "eraser"

        # 存储绘画数据
        self.drawing_data = []

        self.init_ui()


    def init_ui(self):
        # 设置窗口为全屏透明覆盖
        self.setWindowTitle("画板")
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        # ✅ 关键修改：避免系统将完全透明窗口当成“不可交互”
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.99)  # 关键：不能完全透明！
        self.setStyleSheet("background-color: rgba(0, 0, 0, 1);")  # 几乎透明
        self.setFocusPolicy(Qt.StrongFocus)

        # 获取屏幕尺寸
        screen = QApplication.primaryScreen()
        self.screen_rect = screen.availableGeometry()
        self.setGeometry(self.screen_rect)

        # 创建中央部件
        central_widget = QWidget()
        central_widget.setAttribute(Qt.WA_TranslucentBackground)
        central_widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        central_widget.setStyleSheet("background: transparent;")
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建控制面板
        self.create_control_panel()

        # 初始隐藏控制面板
        self.control_panel.hide()

        # 状态标签
        self.status_label = QLabel("按下 Ctrl+Shift+Z 或 Ctrl+鼠标中键 开始绘画")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label, alignment=Qt.AlignBottom | Qt.AlignLeft)

        # ✅ 确保能接收鼠标事件
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # 添加全局快捷键检测
        self.global_shortcut_timer = QTimer()
        self.global_shortcut_timer.timeout.connect(self.check_global_shortcut)
        self.global_shortcut_timer.start(50)
        self.centralWidget().installEventFilter(self)

    def eventFilter(self, obj, event):
        # 捕获全局鼠标事件
        if event.type() == event.MouseButtonPress:
            if QApplication.keyboardModifiers() == Qt.ControlModifier and event.button() == Qt.LeftButton:
                if self.drawing_enabled:
                    # 只在激活时才取消
                    self.toggle_drawing_mode()
                return True
        return super().eventFilter(obj, event)

    def create_control_panel(self):
        # 控制面板容器
        self.control_panel = QFrame()
        self.control_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(45, 45, 45, 220);
                border: 2px solid #5D5D5D;
                border-radius: 15px;
                padding: 10px;
            }
        """)
        self.control_panel.setFixedWidth(300)

        # 控制面板布局
        panel_layout = QVBoxLayout(self.control_panel)

        # 标题
        title = QLabel("画板")
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 5px;
                background-color: rgba(80, 80, 80, 150);
                border-radius: 8px;
            }
        """)
        title.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(title)

        # 工具选择
        tools_layout = QHBoxLayout()

        self.pen_btn = QToolButton()
        self.pen_btn.setText("画笔")
        self.pen_btn.setCheckable(True)
        self.pen_btn.setChecked(True)
        self.pen_btn.clicked.connect(lambda: self.set_tool("pen"))
        self.pen_btn.setStyleSheet("""
            QToolButton {
                background-color: #3498DB;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #2980B9;
            }
        """)

        self.eraser_btn = QToolButton()
        self.eraser_btn.setText("橡皮擦")
        self.eraser_btn.setCheckable(True)
        self.eraser_btn.clicked.connect(lambda: self.set_tool("eraser"))
        self.eraser_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(80, 80, 80, 150);
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: rgba(100, 100, 100, 150);
            }
        """)

        tools_layout.addWidget(self.pen_btn)
        tools_layout.addWidget(self.eraser_btn)
        panel_layout.addLayout(tools_layout)

        # 颜色选择
        color_layout = QHBoxLayout()
        color_label = QLabel("颜色:")
        color_label.setStyleSheet("color: white; font-weight: bold;")
        color_layout.addWidget(color_label)

        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(30, 30)
        self.color_btn.setStyleSheet(
            f"background-color: {self.pen_color.name()}; border-radius: 15px; border: 2px solid white;")
        self.color_btn.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_btn)

        # 预定义颜色
        colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF", "#FFFFFF"]
        for color in colors:
            color_btn = QPushButton()
            color_btn.setFixedSize(20, 20)
            color_btn.setStyleSheet(f"background-color: {color}; border-radius: 10px; border: 1px solid white;")
            color_btn.clicked.connect(lambda checked, c=color: self.set_color(QColor(c)))
            color_layout.addWidget(color_btn)

        color_layout.addStretch()
        panel_layout.addLayout(color_layout)

        # 画笔大小
        size_layout = QHBoxLayout()
        size_label = QLabel("大小:")
        size_label.setStyleSheet("color: white; font-weight: bold;")
        size_layout.addWidget(size_label)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(1, 20)
        self.size_slider.setValue(5)
        self.size_slider.valueChanged.connect(self.set_pen_width)
        self.size_slider.valueChanged.connect(lambda value: self.size_label.setText(str(value)))
        size_layout.addWidget(self.size_slider)

        self.size_label = QLabel("5")
        self.size_label.setStyleSheet("color: white; font-weight: bold; min-width: 20px;")
        size_layout.addWidget(self.size_label)

        panel_layout.addLayout(size_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()

        clear_btn = QPushButton("清空画板")
        clear_btn.clicked.connect(self.clear_canvas)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #2471A3;
            }
        """)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_drawing)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #2471A3;
            }
        """)

        exit_btn = QPushButton("退出")
        exit_btn.clicked.connect(self.close)
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #A93226;
            }
        """)

        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(exit_btn)
        panel_layout.addLayout(btn_layout)

        # 提示信息
        tip_label = QLabel("按下 Ctrl+Shift+Z 或 Ctrl+鼠标中键 绘画模式")
        tip_label.setStyleSheet("color: #AAAAAA; font-size: 10px; padding: 5px;")
        tip_label.setWordWrap(True)
        panel_layout.addWidget(tip_label)

        # 将控制面板添加到主窗口
        self.centralWidget().layout().addWidget(self.control_panel, alignment=Qt.AlignTop | Qt.AlignRight)

    def set_tool(self, tool):
        self.drawing_mode = tool
        self.pen_btn.setChecked(tool == "pen")
        self.eraser_btn.setChecked(tool == "eraser")

        # 更新按钮样式
        if tool == "pen":
            self.pen_btn.setStyleSheet("""
                QToolButton {
                    background-color: #3498DB;
                    color: white;
                    border: none;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background-color: #2980B9;
                }
            """)
            self.eraser_btn.setStyleSheet("""
                QToolButton {
                    background-color: rgba(80, 80, 80, 150);
                    color: white;
                    border: none;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background-color: rgba(100, 100, 100, 150);
                }
            """)
        else:
            self.eraser_btn.setStyleSheet("""
                QToolButton {
                    background-color: #3498DB;
                    color: white;
                    border: none;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background-color: #2980B9;
                }
            """)
            self.pen_btn.setStyleSheet("""
                QToolButton {
                    background-color: rgba(80, 80, 80, 150);
                    color: white;
                    border: none;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background-color: rgba(100, 100, 100, 150);
                }
            """)

    def choose_color(self):
        color = QColorDialog.getColor(self.pen_color, self, "选择画笔颜色")
        if color.isValid():
            self.set_color(color)

    def set_color(self, color):
        self.pen_color = color
        self.color_btn.setStyleSheet(f"background-color: {color.name()}; border-radius: 15px; border: 2px solid white;")
        # 切换到画笔模式
        self.set_tool("pen")

    def set_pen_width(self, width):
        self.pen_width = width

    def toggle_drawing_mode(self):
        self.drawing_enabled = not self.drawing_enabled

        if self.drawing_enabled:
            # 激活绘画模式
            self.status_label.setText("绘画模式已激活 - 按下 Ctrl+Shift+Z 或 Ctrl+鼠标左键 退出绘画模式")
            self.control_panel.show()

            # 确保窗口能接收鼠标事件
            self.setMouseTracking(True)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

            # 设置十字光标
            QApplication.setOverrideCursor(QCursor(Qt.CrossCursor))

            # 确保窗口在最前面
            # 强制窗口激活并接收鼠标事件
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.show()
            self.activateWindow()
            self.raise_()
            QApplication.processEvents()
            self.force_mouse_activation()  # ✅ 新增
        else:
            # 关闭绘画模式
            self.status_label.setText("按下 Ctrl+Shift+Z 或 Ctrl+鼠标中键 开始绘画")
            self.control_panel.hide()

            # 恢复默认光标
            QApplication.restoreOverrideCursor()

            # 清空画布
            self.clear_canvas()

    def force_mouse_activation(self):
        # 模拟一次鼠标按下/释放事件，刷新窗口的鼠标状态
        pos = QCursor.pos()
        press_event = QMouseEvent(QMouseEvent.MouseButtonPress, self.mapFromGlobal(pos),
                                  Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        release_event = QMouseEvent(QMouseEvent.MouseButtonRelease, self.mapFromGlobal(pos),
                                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self, press_event)
        QApplication.sendEvent(self, release_event)

    def save_drawing(self):
        # 创建屏幕截图
        screen = QApplication.primaryScreen()
        if screen:
            pixmap = screen.grabWindow(0)

            # 保存文件对话框
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"drawing_{timestamp}.png"

            file_path, _ = QFileDialog.getSaveFileName(self, "保存绘图", filename, "PNG Files (*.png)")
            if file_path:
                pixmap.save(file_path, "PNG")
                QMessageBox.information(self, "保存成功", f"绘图已保存到: {file_path}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Control:
            self.ctrl_pressed = True

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = False

    def mousePressEvent(self, event):
        # 检测 Ctrl + 鼠标中键 组合
        if self.ctrl_pressed and event.button() == Qt.MiddleButton:
            if self.drawing_enabled:
                # 已激活 → 清空画布
                self.clear_canvas()
            else:
                # 未激活 → 激活绘画
                self.toggle_drawing_mode()
            return

        # 绘画逻辑
        if self.drawing_enabled and event.button() == Qt.LeftButton:
            self.drawing = True
            self.last_point = event.pos()
            # 开始新的路径
            self.drawing_data.append([self.pen_color, self.pen_width, [event.pos()], self.drawing_mode])
            self.update()

    def mouseMoveEvent(self, event):
        if self.drawing and self.drawing_enabled:
            # 添加到当前路径
            if self.drawing_data:
                self.drawing_data[-1][2].append(event.pos())
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drawing and self.drawing_enabled and event.button() == Qt.LeftButton:
            self.drawing = False
            self.update()

    def paintEvent(self, event):
        # 只在激活绘画模式时绘制内容
        if not self.drawing_enabled:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

        # 绘制所有保存的绘画数据
        for data in self.drawing_data:
            color, width, points, mode = data
            if len(points) < 2:
                continue

            if mode == "pen":
                pen = QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            else:  # eraser
                pen = QPen(QColor(0, 0, 0, 0), width * 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                painter.setCompositionMode(QPainter.CompositionMode_Clear)

            painter.setPen(pen)

            # 绘制连续线条
            for i in range(len(points) - 1):
                painter.drawLine(points[i], points[i + 1])

            if mode == "eraser":
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def clear_canvas(self):
        self.drawing_data = []
        self.update()

    def check_global_shortcut(self):
        # 检查Ctrl键是否按下
        ctrl_pressed = QApplication.keyboardModifiers() & Qt.ControlModifier

        # 如果状态变化，更新内部状态
        if ctrl_pressed != self.ctrl_pressed:
            self.ctrl_pressed = ctrl_pressed

    # def start_global_hotkey_listener(self):
    #     # 鼠标监听
    #     def on_click(x, y, button, pressed):
    #         if pressed and self.ctrl_pressed and button == mouse.Button.middle:
    #             # 切换绘画模式
    #             self.trigger_toggle_signal.emit()
    #
    #     # 键盘监听
    #     def on_press(key):
    #         if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
    #             self.ctrl_pressed = True
    #
    #     def on_release(key):
    #         if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
    #             self.ctrl_pressed = False
    #
    #     # 启动监听
    #     mouse.Listener(on_click=on_click).start()
    #     keyboard.Listener(on_press=on_press, on_release=on_release).start()

    def start_global_hotkey_listener(self):
        ctrl_pressed = False
        shift_pressed = False

        def on_click(x, y, button, pressed):
            if pressed and button == mouse.Button.middle:
                if self.drawing_enabled and ctrl_pressed:
                    # 激活状态 → 清屏
                    self.clear_canvas()
                elif not self.drawing_enabled and ctrl_pressed:
                    # 非激活 → 激活
                    self.trigger_toggle_signal.emit()

        def on_press(key):
            nonlocal ctrl_pressed, shift_pressed
            if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                ctrl_pressed = True
            elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
                shift_pressed = True
            elif hasattr(key, 'vk') and key.vk == 0x5A:  # Z 键
                if ctrl_pressed and shift_pressed:
                    self.trigger_toggle_signal.emit()

        def on_release(key):
            nonlocal ctrl_pressed, shift_pressed
            if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                ctrl_pressed = False
            elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
                shift_pressed = False

        with mouse.Listener(on_click=on_click) as mouse_listener, \
                keyboard.Listener(on_press=on_press, on_release=on_release) as kb_listener:
            mouse_listener.join()
            kb_listener.join()


# --------------------- 启动器主界面 ---------------------
class MainLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🧩 画板启动器")
        self.setFixedSize(450, 360)
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #6a11cb, stop:1 #2575fc);
                border-radius: 20px;
            }
        """)

        # 中央布局
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # 标题
        title = QLabel("🎨 画板启动器")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: white;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
            }
        """)
        layout.addWidget(title)

        # 默认颜色选择
        layout.addWidget(QLabel("🎨 默认画笔颜色:"))
        self.color_btn = QPushButton("选择颜色")
        self.color_btn.clicked.connect(self.choose_color)
        self.color_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF4D4D;
                color: white;
                border-radius: 12px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FF6666;
            }
            QPushButton:pressed {
                background-color: #FF2D2D;
            }
        """)
        layout.addWidget(self.color_btn)
        self.pen_color = QColor(255,0,0)

        # 默认笔粗细
        layout.addWidget(QLabel("✏️ 默认笔粗细:"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1,20)
        self.slider.setValue(5)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: #eee;
                height: 10px;
                border-radius: 5px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #FF4D4D, stop:1 #FF0000);
                border: 1px solid #5c5c5c;
                width: 20px;
                margin: -5px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #FF6666;
            }
        """)
        layout.addWidget(self.slider)
        self.pen_width = 5
        self.slider.valueChanged.connect(lambda v: setattr(self,'pen_width',v))

        # 开机自启
        self.autorun_cb = QCheckBox("开机自启")
        self.autorun_cb.setStyleSheet("QCheckBox { color: white; font-weight: bold; }")
        layout.addWidget(self.autorun_cb)

        # 快捷键说明
        hotkey_label = QLabel("⌨️ 快捷键：Ctrl+Shift+Z 激活 / Ctrl+中键 清空")
        hotkey_label.setStyleSheet("color: #DDDDDD; font-size: 12px;")
        layout.addWidget(hotkey_label)

        # 开始按钮
        self.start_btn = QPushButton("🚀 开始绘画")
        self.start_btn.clicked.connect(self.start_drawing)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00E676;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 15px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #33FF88;
            }
            QPushButton:pressed {
                background-color: #00C853;
            }
        """)
        layout.addWidget(self.start_btn)

        layout.addStretch()
        self.tray_icon = None
        self.create_tray_icon()

    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = os.path.join(os.path.dirname(__file__), "tray.png")
        from PyQt5.QtWidgets import QStyle
        self.tray_icon.setIcon(QIcon(icon_path) if os.path.exists(icon_path) else self.style().standardIcon(QStyle.SP_ComputerIcon))
        menu = QMenu()
        open_action = QAction("打开主界面", self)
        open_action.triggered.connect(self.showNormal)
        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(open_action)
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.pen_color = color
            self.color_btn.setStyleSheet(f"background-color: {color.name()}; color:white; border-radius:8px;")

    def start_drawing(self):
        if self.autorun_cb.isChecked():
            self.set_autorun(True)
        else:
            self.set_autorun(False)

        self.hide()
        self.tray_icon.showMessage("画板", "程序已最小化到托盘", QSystemTrayIcon.Information, 2000)

        # ✅ 如果绘画窗口已经存在，就直接显示，否则创建一个
        if hasattr(self, 'overlay') and self.overlay is not None:
            self.overlay.showFullScreen()
            self.overlay.raise_()
            self.overlay.activateWindow()
        else:
            self.overlay = DrawingOverlay(pen_color=self.pen_color, pen_width=self.pen_width)
            self.overlay.showFullScreen()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage("画板","程序已最小化到托盘",QSystemTrayIcon.Information,2000)

    def set_autorun(self, enable):
        key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_path = sys.executable
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_ALL_ACCESS) as reg_key:
            if enable:
                winreg.SetValueEx(reg_key, "TransparentDrawing", 0, winreg.REG_SZ, app_path)
            else:
                try: winreg.DeleteValue(reg_key,"TransparentDrawing")
                except FileNotFoundError: pass

# --------------------- 程序入口 ---------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("画板")
    app.setStyle('Fusion')

    launcher = MainLauncher()
    launcher.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()