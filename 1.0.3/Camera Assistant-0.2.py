import os
import sys  # 导入sys模块
import shutil
import time
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel, 
                            QFileDialog, QTextEdit, QProgressBar, QHBoxLayout, 
                            QVBoxLayout, QWidget, QComboBox, QLineEdit, QGroupBox,
                            QFormLayout, QFontComboBox, QTabWidget,
                            QMessageBox, QRadioButton, QButtonGroup, QGraphicsDropShadowEffect,
                            QSplashScreen, QScrollArea, QAction, QSystemTrayIcon)  
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QPoint, QTimer  # 新增QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor  # QColor移至此处导入

class FileTransferThread(QThread):
    """文件传输线程，用于在后台处理文件移动，避免UI卡顿"""
    progress_updated = pyqtSignal(int)
    log_updated = pyqtSignal(str)
    transfer_complete = pyqtSignal()
    speed_updated = pyqtSignal(str)
    file_count_updated = pyqtSignal(int, int)  # 当前数量, 总数量
    
    def __init__(self, source_folder, dest_folder, file_list, file_type_filter, 
                 custom_extensions=None, duplicate_handling=1):
        super().__init__()
        self.source_folder = source_folder
        self.dest_folder = dest_folder
        self.file_list = file_list
        self.file_type_filter = file_type_filter  # 过滤的文件类型
        self.custom_extensions = custom_extensions if custom_extensions else []  # 自定义扩展名
        self.duplicate_handling = duplicate_handling  # 1:重命名, 2:覆盖, 3:跳过
        self.running = True
        self.paused = False
        self.stopped = False
        
    def run(self):
        total_files = len(self.file_list)
        processed_files = 0
        start_time = time.time()
        last_time = start_time
        last_processed = 0
        
        for filename in self.file_list:
            if self.stopped:
                self.log_updated.emit("操作已停止！")
                break
            if not self.running:
                while self.paused and not self.stopped:
                    time.sleep(0.1)
                if self.stopped:
                    self.log_updated.emit("操作已停止！")
                    break
            
            try:
                # 根据选择的文件类型进行过滤
                if self.should_process_file(filename):
                    file_path = os.path.join(self.source_folder, filename)
                    result = self.move_file_to_date_folder(file_path, self.dest_folder)
                    if result:
                        self.log_updated.emit(result)
            
            except Exception as e:
                self.log_updated.emit(f"处理 {filename} 时出错: {str(e)}！")
            
            processed_files += 1
            progress = int((processed_files / total_files) * 100)
            self.progress_updated.emit(progress)
            self.file_count_updated.emit(processed_files, total_files)
            
            # 计算传输速度
            current_time = time.time()
            if current_time - last_time >= 1:  # 每秒更新一次速度
                files_per_sec = (processed_files - last_processed) / (current_time - last_time) if (current_time - last_time) > 0 else 0
                self.speed_updated.emit(f"{files_per_sec:.1f} 个文件/秒")
                last_time = current_time
                last_processed = processed_files
        
        self.transfer_complete.emit()
    
    def should_process_file(self, filename):
        """根据选择的文件类型判断是否处理该文件"""
        filename_lower = filename.lower()
        
        # 图片文件
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.raw')
        # 视频文件
        video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.mpeg', '.mpg', '.3gp')
        # LRV文件
        lrv_extension = '.lrv'
        
        # 处理自定义格式
        if self.file_type_filter == "custom" and self.custom_extensions:
            return any(filename_lower.endswith(ext.lower()) for ext in self.custom_extensions)
                
        if self.file_type_filter == "all" or self.file_type_filter == "images":
            if filename_lower.endswith(image_extensions):
                return True
                
        if self.file_type_filter == "all" or self.file_type_filter == "videos":
            if filename_lower.endswith(video_extensions):
                return True
                
        if self.file_type_filter == "all" or self.file_type_filter == "lrv":
            if filename_lower.endswith(lrv_extension):
                return True
                
        return False
    
    def pause(self):
        self.paused = True
        self.running = False
    
    def resume(self):
        self.paused = False
        self.running = True
    
    def stop(self):
        self.stopped = True
        self.running = False
        self.paused = False
    
    def get_file_date(self, file_path):
        """获取文件的日期信息，支持图片、视频和LRV文件"""
        try:
            # 对于图片文件，尝试从EXIF获取日期
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.raw')):
                with Image.open(file_path) as image:
                    exif_data = image._getexif()
                    if exif_data:
                        for tag, value in exif_data.items():
                            decoded = TAGS.get(tag, tag)
                            if decoded in ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']:
                                return value
            
            # 对于其他文件，使用文件修改日期
            mtime = os.path.getmtime(file_path)
            return datetime.fromtimestamp(mtime).strftime('%Y:%m:%d %H:%M:%S')
            
        except Exception as e:
            self.log_updated.emit(f"获取 {os.path.basename(file_path)} 日期时出错: {str(e)}！")
            return None
    
    def move_file_to_date_folder(self, file_path, destination_folder):
        """将文件移动到以日期命名的文件夹中，处理同名文件"""
        date = self.get_file_date(file_path)
        if date:
            try:
                # 处理不同格式的日期字符串
                if ':' in date:
                    if date.count(':') >= 2:
                        year_month = date.split(':')[0] + '-' + date.split(':')[1]
                    else:
                        #  fallback 到文件修改时间
                        mtime = os.path.getmtime(file_path)
                        date = datetime.fromtimestamp(mtime).strftime('%Y:%m:%d %H:%M:%S')
                        year_month = date.split(':')[0] + '-' + date.split(':')[1]
                else:
                    # 处理其他日期格式
                    year_month = date[:7]
                
                folder_path = os.path.join(destination_folder, year_month)
                os.makedirs(folder_path, exist_ok=True)
                
                dest_path = os.path.join(folder_path, os.path.basename(file_path))
                
                # 处理同名文件
                if os.path.exists(dest_path):
                    if self.duplicate_handling == 1:  # 重命名
                        counter = 1
                        name, ext = os.path.splitext(os.path.basename(file_path))
                        while os.path.exists(dest_path):
                            dest_path = os.path.join(folder_path, f"{name}_{counter}{ext}")
                            counter += 1
                        action = "重命名并移动"
                    elif self.duplicate_handling == 2:  # 覆盖
                        action = "覆盖并移动"
                    else:  # 跳过
                        return f"已跳过同名文件: {os.path.basename(file_path)}"
                else:
                    action = "已移动~"
                
                # 使用shutil.move移动文件，支持跨设备
                shutil.move(file_path, dest_path)
                return f"{action}: {os.path.basename(file_path)} -> {year_month}"
                
            except Exception as e:
                return f"移动 {os.path.basename(file_path)} 失败: {str(e)}！"
        else:
            # 将无法获取日期的文件移动到"unknown_date"文件夹
            try:
                folder_path = os.path.join(destination_folder, "unknown_date")
                os.makedirs(folder_path, exist_ok=True)
                dest_path = os.path.join(folder_path, os.path.basename(file_path))
                
                # 处理同名文件
                if os.path.exists(dest_path):
                    if self.duplicate_handling == 1:  # 重命名
                        counter = 1
                        name, ext = os.path.splitext(os.path.basename(file_path))
                        while os.path.exists(dest_path):
                            dest_path = os.path.join(folder_path, f"{name}_{counter}{ext}")
                            counter += 1
                        action = "重命名并移动"
                    elif self.duplicate_handling == 2:  # 覆盖
                        action = "覆盖并移动"
                    else:  # 跳过
                        return f"已跳过同名文件: {os.path.basename(file_path)} (unknown_date)"
                
                shutil.move(file_path, dest_path)
                return f"{action if os.path.exists(dest_path) else '已移动'}: {os.path.basename(file_path)} -> unknown_date"
                
            except Exception as e:
                return f"移动 {os.path.basename(file_path)} 失败: {str(e)}"

class MediaOrganizer(QMainWindow):
    """媒体文件整理工具主窗口"""
    def __init__(self):
        super().__init__()
        self.transfer_thread = None
        self.settings = QSettings("MediaOrganizer", "Settings")
        self.base_font_size = 10  # 基础字体大小，用于缩放
        self.scale_factor = 1.0   # 缩放因子
        self.shadow_effects = {}  # 存储阴影效果的字典
        
        # 初始化窗口和系统托盘图标
        try:
            # 获取应用图标路径 - 兼容PyInstaller打包
            if hasattr(sys, '_MEIPASS'):
                # 当程序被PyInstaller打包时，使用临时目录中的资源
                icon_path = os.path.join(sys._MEIPASS, "CA-2025.ico")
            else:
                # 在开发环境中使用当前目录下的图标
                script_dir = os.path.dirname(os.path.abspath(__file__))
                icon_path = os.path.join(script_dir, "CA-2025.ico")
            
            # 设置窗口和托盘图标
            if os.path.exists(icon_path):
                # 设置窗口图标（任务栏显示）
                self.setWindowIcon(QIcon(icon_path))
                
                # 创建系统托盘图标
                self.tray_icon = QSystemTrayIcon(self)
                self.tray_icon.setIcon(QIcon(icon_path))
                self.tray_icon.setToolTip("CA-2025 Camera Assistant v1.0.3")
                
                # 创建托盘菜单
                show_action = QAction("显示窗口", self)
                show_action.triggered.connect(self.show)
                
                exit_action = QAction("退出", self)
                exit_action.triggered.connect(self.close)
                
                # 添加菜单项
                tray_menu = [show_action, exit_action]
                self.tray_icon.setContextMenu(self.create_context_menu(tray_menu))
                
                # 显示托盘图标
                self.tray_icon.show()
                
                # 连接托盘图标点击事件
                self.tray_icon.activated.connect(self.tray_icon_activated)
            else:
                # 图标文件不存在时的容错处理
                self.tray_icon = None
        except Exception as e:
            # 异常处理，确保程序不会因为图标问题而崩溃
            self.tray_icon = None
        
        self.init_ui()
    
    def create_context_menu(self, actions):
        """创建上下文菜单"""
        from PyQt5.QtWidgets import QMenu
        menu = QMenu()
        for action in actions:
            menu.addAction(action)
        return menu
    
    def tray_icon_activated(self, reason):
        """处理托盘图标的点击事件"""
        if reason == QSystemTrayIcon.Trigger:
            # 单击显示/隐藏窗口
            if self.isHidden():
                self.show()
                self.raise_()
            else:
                self.hide()
    
    def closeEvent(self, event):
        """处理窗口关闭事件
        
        当用户点击关闭按钮时，如果系统托盘图标存在并可见，
        则将窗口隐藏到托盘而不是完全退出应用程序。
        如果没有托盘图标，则正常关闭窗口。
        """
        if self.tray_icon and self.tray_icon.isVisible():
            self.hide()  # 隐藏窗口到托盘
            event.ignore()  # 忽略关闭事件
        else:
            event.accept()  # 正常关闭窗口
        
    def init_ui(self):
        """初始化用户界面组件和布局"""
        # 设置窗口标题，包含版本信息
        self.setWindowTitle("CA-2025 Camera Assistant  v1.0.3 -Au987")
        self.setGeometry(100, 100, 1000, 850)
        # 设置窗口最小尺寸，确保界面元素正常显示
        self.setMinimumSize(600, 500)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)  # 确保滚动区域内的部件可以调整大小
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 水平滚动条按需显示
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)    # 垂直滚动条按需显示
        
        # 创建主布局容器，放在滚动区域内
        scroll_content = QWidget()
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 创建顶部标签页
        self.tab_widget = QTabWidget()
        
        # 主功能标签页
        main_tab = QWidget()
        main_tab_layout = QVBoxLayout(main_tab)
        main_tab_layout.setContentsMargins(5, 5, 5, 5)
        main_tab_layout.setSpacing(10)
        
        # 设置标签页
        settings_tab = QWidget()
        settings_tab_layout = QVBoxLayout(settings_tab)
        settings_tab_layout.setContentsMargins(10, 10, 10, 10)
        settings_tab_layout.setSpacing(15)
        
        self.tab_widget.addTab(main_tab, "主功能")
        self.tab_widget.addTab(settings_tab, "设置")
        
        # ================ 主功能标签页内容 ================
        
        # 创建地址设置区域
        self.address_group = QGroupBox("文件夹设置")
        address_layout = QFormLayout()
        address_layout.setRowWrapPolicy(QFormLayout.DontWrapRows)
        address_layout.setSpacing(10)
        
        # 源文件夹选择
        self.source_edit = QLineEdit()
        self.source_btn = QPushButton("浏览...")
        self.source_btn.clicked.connect(self.select_source_folder)
        
        source_layout = QHBoxLayout()
        source_layout.addWidget(self.source_edit, 7)
        source_layout.addWidget(self.source_btn, 1)
        
        # 目标文件夹选择
        self.dest_edit = QLineEdit()
        self.dest_btn = QPushButton("浏览...")
        self.dest_btn.clicked.connect(self.select_dest_folder)
        
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(self.dest_edit, 7)
        dest_layout.addWidget(self.dest_btn, 1)
        
        # 文件类型选择
        self.file_type_combo = QComboBox()
        self.file_type_combo.addItems(["所有支持的文件", "仅图片", "仅视频", "仅LRV文件", "自定义格式"])
        self.file_type_combo.setCurrentIndex(0)
        self.file_type_combo.currentIndexChanged.connect(self.on_file_type_changed)
        
        # 自定义格式输入框
        self.custom_extensions_edit = QLineEdit()
        self.custom_extensions_edit.setPlaceholderText("例如: .txt,.pdf,.zip (用逗号分隔)")
        self.custom_extensions_edit.setEnabled(False)  # 默认禁用
        
        # 常用地址下拉框
        self.common_source_combo = QComboBox()
        self.common_dest_combo = QComboBox()
        self.common_source_combo.currentIndexChanged.connect(self.on_source_changed)
        self.common_dest_combo.currentIndexChanged.connect(self.on_dest_changed)
        
        # 加载保存的地址
        self.load_saved_paths()
        
        address_layout.addRow("源文件夹:", source_layout)
        address_layout.addRow("常用源地址:", self.common_source_combo)
        address_layout.addRow("目标文件夹:", dest_layout)
        address_layout.addRow("常用目标地址:", self.common_dest_combo)
        address_layout.addRow("文件类型:", self.file_type_combo)
        address_layout.addRow("自定义格式:", self.custom_extensions_edit)
        
        self.address_group.setLayout(address_layout)
        main_tab_layout.addWidget(self.address_group)
        
        # 同名文件处理设置
        self.duplicate_group = QGroupBox("同名文件处理")
        duplicate_layout = QVBoxLayout()
        
        self.duplicate_button_group = QButtonGroup(self)
        
        self.rename_radio = QRadioButton("自动重命名（例如：file.jpg → file_1.jpg）")
        self.overwrite_radio = QRadioButton("覆盖现有文件")
        self.skip_radio = QRadioButton("跳过同名文件")
        
        self.duplicate_button_group.addButton(self.rename_radio, 1)
        self.duplicate_button_group.addButton(self.overwrite_radio, 2)
        self.duplicate_button_group.addButton(self.skip_radio, 3)
        
        # 默认选择重命名
        self.rename_radio.setChecked(True)
        
        duplicate_layout.addWidget(self.rename_radio)
        duplicate_layout.addWidget(self.overwrite_radio)
        duplicate_layout.addWidget(self.skip_radio)
        
        self.duplicate_group.setLayout(duplicate_layout)
        main_tab_layout.addWidget(self.duplicate_group)
        
        # 创建按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.start_btn = QPushButton("开始整理")
        self.start_btn.setIcon(self.style().standardIcon(self.style().SP_MediaPlay))
        self.start_btn.clicked.connect(self.start_organizing)
        
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setIcon(self.style().standardIcon(self.style().SP_MediaPause))
        self.pause_btn.clicked.connect(self.pause_organizing)
        self.pause_btn.setEnabled(False)
        
        self.resume_btn = QPushButton("继续")
        self.resume_btn.setIcon(self.style().standardIcon(self.style().SP_MediaSkipForward))
        self.resume_btn.clicked.connect(self.resume_organizing)
        self.resume_btn.setEnabled(False)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setIcon(self.style().standardIcon(self.style().SP_MediaStop))
        self.stop_btn.clicked.connect(self.stop_organizing)
        self.stop_btn.setEnabled(False)
        
        self.save_paths_btn = QPushButton("保存当前地址")
        self.save_paths_btn.setIcon(self.style().standardIcon(self.style().SP_DialogSaveButton))
        self.save_paths_btn.clicked.connect(self.save_current_paths)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.resume_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_paths_btn)
        
        main_tab_layout.addLayout(btn_layout)
        
        # 进度和状态区域
        self.progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout()
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        # 状态信息
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("font-weight: bold;")
        
        self.file_count_label = QLabel("文件: 0/0")
        
        self.speed_label = QLabel("速度: --")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.file_count_label)
        status_layout.addWidget(self.speed_label)
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addLayout(status_layout)
        self.progress_group.setLayout(progress_layout)
        main_tab_layout.addWidget(self.progress_group)
        
        # 日志区域
        self.log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        
        log_layout.addWidget(self.log_text)
        self.log_group.setLayout(log_layout)
        
        main_tab_layout.addWidget(self.log_group, 1)
        
        # ================ 设置标签页内容 ================
        
        # 字体设置
        self.font_group = QGroupBox("字体设置")
        font_layout = QFormLayout()
        
        self.font_combo = QFontComboBox()
        
        # 字体大小下拉选择框
        self.font_size_combo = QComboBox()
        # 添加常用字体大小选项
        font_sizes = ["8", "9", "10", "11", "12", "14", "16", "18", "20", "22", "24"]
        self.font_size_combo.addItems(font_sizes)
        self.font_size_combo.setCurrentText("10")  # 默认10号字体
        
        self.apply_font_btn = QPushButton("应用字体设置")
        self.apply_font_btn.clicked.connect(self.apply_font_settings)
        
        font_layout.addRow("字体:", self.font_combo)
        font_layout.addRow("字体大小:", self.font_size_combo)
        font_layout.addRow(self.apply_font_btn)
        
        self.font_group.setLayout(font_layout)
        settings_tab_layout.addWidget(self.font_group)
        
        # 界面缩放设置
        self.scale_group = QGroupBox("界面缩放")
        scale_layout = QFormLayout()
        
        self.scale_spin = QComboBox()
        # 缩放选项下拉框
        scale_options = ["80%", "90%", "100%", "110%", "120%", "130%", "140%", "150%"]
        self.scale_spin.addItems(scale_options)
        self.scale_spin.setCurrentText("100%")
        
        self.apply_scale_btn = QPushButton("应用缩放设置")
        self.apply_scale_btn.clicked.connect(self.apply_scale_settings)
        
        scale_layout.addRow("缩放比例:", self.scale_spin)
        scale_layout.addRow(self.apply_scale_btn)
        
        self.scale_group.setLayout(scale_layout)
        settings_tab_layout.addWidget(self.scale_group)
        
        # 外观设置（已移除图标设置）
        self.appearance_group = QGroupBox("外观设置")
        appearance_layout = QVBoxLayout()
        
        theme_label = QLabel("主题:")
        theme_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        
        # 包含默认主题和深色主题
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([
            "默认主题",  # 设置为第一个默认选项
            "深色主题",  # 深色主题
            "珊瑚橙主题", "橄榄绿主题", "靛蓝色主题", 
            "薰衣草紫主题", "薄荷青主题", "琥珀黄主题",
            "玫瑰粉主题", "石板灰主题", "翡翠绿主题", "天空蓝主题",
            "夕阳红主题", "深海蓝主题", "秋叶橙主题",
            "嫩芽绿主题", "葡萄紫主题", "沙石棕主题",
            "冰雪白主题", "墨黑灰主题", "樱花粉主题", "湖水青主题"
        ])
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        
        # 边框风格设置
        border_label = QLabel("边框风格:")
        border_label.setStyleSheet("font-weight: bold; margin-top: 10px; margin-bottom: 5px;")
        
        self.border_style_combo = QComboBox()
        self.border_style_combo.addItems(["圆角边框", "直角边框", "阴影边框", "简约边框"])
        self.border_style_combo.currentIndexChanged.connect(self.change_border_style)
        
        appearance_layout.addWidget(theme_label)
        appearance_layout.addWidget(self.theme_combo)
        appearance_layout.addWidget(border_label)
        appearance_layout.addWidget(self.border_style_combo)
        
        self.appearance_group.setLayout(appearance_layout)
        settings_tab_layout.addWidget(self.appearance_group)

        self.about_group = QGroupBox("关于")
        about_layout = QVBoxLayout()
        
        about_text = QLabel("""
       <h1>CA-2025 (Camera Assistant)</h1>
        <p><strong>版本信息</strong><br>
        当前版本: 1.0.3 正式版<br>
        发布日期: 2025年9月29日<br>
        开发维护: Au</p>

        <h3>软件简介</h3>
        <p>CA-2025是一款轻量级开源媒体文件管理工具</p>
        <p>专为摄影爱好者和专业用户设计，旨在解决SD/TF/CF卡等媒体文件的快速整理需求。</p>
        <p>通过优化文件读取与传输逻辑，绕过传统文件管理器的低效机制</p>
        <p>实现媒体文件的高速分类与迁移，同时提供直观的操作界面和灵活的自定义选项。</p>

        <h3>使用指南</h3>
        <ol>
        <li><strong>设置路径</strong>：通过"浏览"按钮选择源文件夹（如SD卡目录）和目标文件夹（如电脑存储路径）</li>
        <li><strong>保存路径</strong>：可保存常用地址以便后续使用哦</li>
        <li><strong>文件类型</strong>：滑动滚轮选择需要处理的文件类型（所有支持文件/仅图片/仅视频等）用滚轮!</li>
        <li><strong>自定义格式</strong>：选择"自定义格式"时需输入扩展名（用逗号分隔）</li>
        <li><strong>重复策略</strong>：选择遇到同名文件时的处理方式（默认自动重命名）</li>
        <li><strong>开始操作</strong>：点击"开始整理"启动处理，可通过"暂停"/"继续"控制过程，或"停止"终止操作</li>
        <li><strong>查看进度</strong>：通过进度条、文件计数和传输速度了解处理状态，操作日志会记录详细过程</li>
        </ol>

        <h3>核心功能</h3>
        <ul>
        <li><strong>智能分类</strong>：根据文件的创建日期（优先读取EXIF信息）或修改日期，自动整理到"年-月"格式的文件夹中</li>
        <li><strong>多格式</strong>：默认支持（.png/.jpg/.jpeg/.mp4/.avi/.mov）多种格式，同时支持自定义文件格式</li>
        <li><strong>重复处理</strong>：提供三种策略（自动重命名/覆盖/跳过），灵活应对同名文件场景~~</li>
        <li><strong>高效后台</strong>：采用多线程技术，文件传输过程中不阻塞界面操作，实时显示进度与速度~</li>
        <li><strong>个性界面</strong>：支持字体设置、界面缩放、主题切换（含深色主题等20+风格）和边框样式自定义~~~</li>
        <li><strong>地址管理</strong>：可保存常用源文件夹和目标文件夹地址，简化重复操作哦</li>
        </ul>

        <h3>法律信息</h3>
        <ul>
        <li><strong>开源声明</strong>：本软件完全开源免费,允许非商业用途的修改与分发哦~~</li>
        <li><strong>隐私保护</strong>：程序运行过程中不收集任何用户个人信息、文件内容及设备数据~~~</li>
        <li><strong>错误反馈</strong>：如遇程序错误,联系作者，并附上详细报错信息以便修复@Au</li>
        <li><strong>版权说明</strong>：软件图标采用原创素材，若涉及著作权问题，请联系作者哦</li>
        </ul>

        <h3>注意事项</h3>
        <ul>
        <li>处理大量文件时，建议保持源设备（如SD卡）连接稳定，避免中途断开导致文件损坏哦</li>
        <li>无法获取日期信息的文件会被自动归类到"unknown_date"文件夹哦</li>
        <li>跨设备传输（如从SD卡到电脑硬盘）速度可能受硬件接口限制哦!</li>
        <li>界面缩放和字体设置调整后，需点击"应用"按钮生效哦!</li>
        </ul>""")
        about_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        about_text.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        
        about_layout.addWidget(about_text)
        self.about_group.setLayout(about_layout)
        settings_tab_layout.addWidget(self.about_group)
        
        settings_tab_layout.addStretch()
        
        # 将标签页添加到主布局
        main_layout.addWidget(self.tab_widget)
        
        # 设置滚动区域的部件
        scroll_area.setWidget(scroll_content)
        
        # 设置主窗口部件为滚动区域
        self.setCentralWidget(scroll_area)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
        # 加载保存的设置
        self.load_settings()
        # 应用初始样式
        self.apply_font_settings()
        self.change_theme(self.theme_combo.currentIndex())
    
    def on_file_type_changed(self, index):
        """文件类型选择变化时处理"""
        # 当选择自定义格式时启用输入框，否则禁用
        self.custom_extensions_edit.setEnabled(index == 4)  # 4是"自定义格式"的索引
    
    def load_settings(self):
        """加载保存的应用设置，修复字体大小类型错误"""
        # 加载字体设置
        font_family = self.settings.value("font_family", "SimHei")
        
        # 修复字体大小类型错误
        try:
            # 尝试获取保存的字体大小
            font_size = self.settings.value("font_size", "10")
            # 确保是字符串类型
            font_size_str = str(font_size)
            
            # 检查是否在可用选项中
            valid_sizes = [self.font_size_combo.itemText(i) for i in range(self.font_size_combo.count())]
            if font_size_str in valid_sizes:
                self.font_size_combo.setCurrentText(font_size_str)
            else:
                self.font_size_combo.setCurrentText("10")  # 使用默认值
                font_size_str = "10"
                
            self.base_font_size = int(font_size_str)
        except Exception as e:
            self.log(f"加载字体设置出错: {str(e)}，使用默认设置！")
            self.font_size_combo.setCurrentText("10")
            self.base_font_size = 10
        
        self.font_combo.setCurrentFont(QFont(font_family))
        
        # 加载缩放设置
        try:
            scale = self.settings.value("scale_factor", "100%")
            index = self.scale_spin.findText(scale)
            if index >= 0:
                self.scale_spin.setCurrentIndex(index)
            self.scale_factor = int(scale.replace("%", "")) / 100.0
        except Exception as e:
            self.log(f"加载缩放设置出错: {str(e)}，使用默认设置！")
            self.scale_spin.setCurrentText("100%")
            self.scale_factor = 1.0
        
        # 加载主题设置 - 设置默认主题为第一个选项
        try:
            theme = self.settings.value("theme", "默认主题")
            index = self.theme_combo.findText(theme)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)
            else:
                self.theme_combo.setCurrentIndex(0)  # 默认主题
        except Exception as e:
            self.log(f"加载主题设置出错: {str(e)}，使用默认主题！")
            self.theme_combo.setCurrentIndex(0)  # 默认主题
            
        # 加载边框风格设置
        try:
            border_style = self.settings.value("border_style", "圆角边框")
            index = self.border_style_combo.findText(border_style)
            if index >= 0:
                self.border_style_combo.setCurrentIndex(index)
        except Exception as e:
            self.log(f"加载边框设置出错: {str(e)}，使用默认设置！")
            self.border_style_combo.setCurrentIndex(0)
            
        # 加载同名文件处理设置
        try:
            duplicate_handling = int(self.settings.value("duplicate_handling", 1))
            self.duplicate_button_group.button(duplicate_handling).setChecked(True)
        except Exception as e:
            self.log(f"加载文件处理设置出错: {str(e)}，使用默认设置！")
            self.duplicate_button_group.button(1).setChecked(True)  # 默认重命名
    
    def save_settings(self):
        """保存应用设置"""
        self.settings.setValue("font_family", self.font_combo.currentFont().family())
        self.settings.setValue("font_size", self.font_size_combo.currentText())
        self.settings.setValue("scale_factor", self.scale_spin.currentText())
        self.settings.setValue("theme", self.theme_combo.currentText())
        self.settings.setValue("border_style", self.border_style_combo.currentText())
        self.settings.setValue("duplicate_handling", self.duplicate_button_group.checkedId())
    
    def apply_scale_settings(self):
        """应用界面缩放设置"""
        scale_text = self.scale_spin.currentText()
        scale = int(scale_text.replace("%", ""))
        self.scale_factor = scale / 100.0
        self.apply_font_settings()  # 缩放时同时更新字体
        self.log(f"已应用界面缩放: {scale}%")
        self.save_settings()
        # 重新应用边框样式以适应缩放
        self.change_border_style(self.border_style_combo.currentIndex())
    
    def apply_font_settings(self):
        """应用字体设置到全局"""
        font = self.font_combo.currentFont()
        base_size = int(self.font_size_combo.currentText())
        scaled_size = int(base_size * self.scale_factor)
        
        # 设置应用全局字体
        app = QApplication.instance()
        font.setPointSize(scaled_size)
        app.setFont(font)
        
        # 单独调整一些控件的大小
        button_height = int(30 * self.scale_factor)
        edit_height = int(32 * self.scale_factor)  # 增加输入框高度，确保字体完全显示
        combo_height = int(32 * self.scale_factor)  # 增加下拉框高度
        
        # 调整按钮大小
        for btn in [self.start_btn, self.pause_btn, self.resume_btn, 
                   self.stop_btn, self.save_paths_btn, self.apply_font_btn,
                   self.apply_scale_btn, self.source_btn, self.dest_btn]:
            btn.setMinimumHeight(button_height)
            btn.setStyleSheet(f"padding: {int(6 * self.scale_factor)}px {int(12 * self.scale_factor)}px;")
        
        # 调整输入框大小和样式，确保字体完全显示
        input_padding = int(8 * self.scale_factor)  # 增加内边距
        for edit in [self.source_edit, self.dest_edit, self.custom_extensions_edit]:
            edit.setMinimumHeight(edit_height)
            edit.setStyleSheet(f"padding: {input_padding}px;")
        
        # 调整下拉框大小
        for combo in [self.file_type_combo, self.common_source_combo, 
                     self.common_dest_combo, self.theme_combo, self.font_combo,
                     self.border_style_combo, self.font_size_combo, self.scale_spin]:
            combo.setMinimumHeight(combo_height)
            combo.setStyleSheet(f"padding: {input_padding}px;")
        
        # 调整进度条高度
        self.progress_bar.setMinimumHeight(int(22 * self.scale_factor))
        
        # 保存字体设置
        self.save_settings()
        self.log(f"已应用字体设置: {font.family()} {scaled_size}pt~")
    
    def get_border_style(self):
        """根据选择的边框风格返回CSS样式"""
        border_style = self.border_style_combo.currentText()
        border_width = int(1.0 * self.scale_factor)  # 减小边框宽度
        
        if border_style == "圆角边框":
            return f"border: {border_width}px solid; border-radius: {int(6 * self.scale_factor)}px;"
        elif border_style == "直角边框":
            return f"border: {border_width}px solid; border-radius: 0px;"
        elif border_style == "简约边框":
            return f"border: {int(0.5 * self.scale_factor)}px solid; border-radius: {int(2 * self.scale_factor)}px;"
        else:  # 阴影边框，只返回基础边框样式，阴影将通过QGraphicsDropShadowEffect添加
            return f"border: {border_width}px solid; border-radius: {int(4 * self.scale_factor)}px;"
    
    def create_shadow_effect(self, widget, color):
        """为控件创建阴影效果"""
        # 如果已有阴影效果，先移除
        if widget in self.shadow_effects:
            widget.setGraphicsEffect(None)
        
        # 创建新的阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setColor(color)  # color是QColor对象
        shadow.setBlurRadius(5 * self.scale_factor)
        shadow.setOffset(2 * self.scale_factor, 2 * self.scale_factor)
        
        # 应用阴影效果
        widget.setGraphicsEffect(shadow)
        self.shadow_effects[widget] = shadow
        return shadow
    
    def remove_all_shadows(self):
        """移除所有控件的阴影效果"""
        for widget in self.shadow_effects:
            widget.setGraphicsEffect(None)
        self.shadow_effects.clear()
    
    def change_border_style(self, index):
        """更改边框风格并重新应用主题"""
        self.save_settings()
        
        # 阴影边框需要特殊处理
        border_style = self.border_style_combo.currentText()
        
        # 如果不是阴影边框，移除所有阴影
        if border_style != "阴影边框":
            self.remove_all_shadows()
        else:
            # 对于阴影边框，根据当前主题创建阴影效果
            theme_index = self.theme_combo.currentIndex()
            # 确定阴影颜色 - 返回QColor对象
            shadow_color = self.get_shadow_color(theme_index)
            
            # 为主要分组控件添加阴影
            for widget in [self.address_group, self.duplicate_group, 
                          self.progress_group, self.log_group,
                          self.font_group, self.scale_group,
                          self.appearance_group, self.about_group]:
                self.create_shadow_effect(widget, shadow_color)
        
        self.change_theme(self.theme_combo.currentIndex())  # 重新应用主题以更新边框
        self.log(f"已应用边框风格: {self.border_style_combo.currentText()}~")
    
    def get_shadow_color(self, theme_index):
        """获取阴影颜色，返回QColor对象"""
        # 定义RGBA值，每个主题的阴影颜色
        shadow_rgba = [
            (22, 93, 255, 51),   # 默认主题 - rgba(22, 93, 255, 0.2)
            (0, 168, 255, 51),   # 深色主题 - rgba(0, 168, 255, 0.2)
            (255, 127, 80, 51),  # 珊瑚橙主题 - rgba(255, 127, 80, 0.2)
            (85, 139, 47, 51),   # 橄榄绿主题 - rgba(85, 139, 47, 0.2)
            (63, 81, 181, 51),   # 靛蓝色主题 - rgba(63, 81, 181, 0.2)
            (156, 39, 176, 51),  # 薰衣草紫主题 - rgba(156, 39, 176, 0.2)
            (38, 166, 154, 51),  # 薄荷青主题 - rgba(38, 166, 154, 0.2)
            (255, 179, 0, 51),   # 琥珀黄主题 - rgba(255, 179, 0, 0.2)
            (216, 27, 96, 51),   # 玫瑰粉主题 - rgba(216, 27, 96, 0.2)
            (120, 144, 156, 51), # 石板灰主题 - rgba(120, 144, 156, 0.2)
            (0, 200, 83, 51),    # 翡翠绿主题 - rgba(0, 200, 83, 0.2)
            (25, 118, 210, 51),  # 天空蓝主题 - rgba(25, 118, 210, 0.2)
            (229, 57, 53, 51),   # 夕阳红主题 - rgba(229, 57, 53, 0.2)
            (21, 101, 192, 51),  # 深海蓝主题 - rgba(21, 101, 192, 0.2)
            (245, 124, 0, 51),   # 秋叶橙主题 - rgba(245, 124, 0, 0.2)
            (102, 187, 106, 51), # 嫩芽绿主题 - rgba(102, 187, 106, 0.2)
            (142, 36, 170, 51),  # 葡萄紫主题 - rgba(142, 36, 170, 0.2)
            (161, 136, 127, 51), # 沙石棕主题 - rgba(161, 136, 127, 0.2)
            (189, 189, 189, 51), # 冰雪白主题 - rgba(189, 189, 189, 0.2)
            (97, 97, 97, 51),    # 墨黑灰主题 - rgba(97, 97, 97, 0.2)
            (236, 64, 122, 51),  # 樱花粉主题 - rgba(236, 64, 122, 0.2)
            (66, 165, 245, 51)   # 湖水青主题 - rgba(66, 165, 245, 0.2)
        ]
        
        # 转换为QColor对象，注意alpha值范围是0-255
        r, g, b, a = shadow_rgba[theme_index]
        return QColor(r, g, b, a)
    
    def change_theme(self, index):
        """更改应用主题，优化标签页选中效果"""
        # 计算基于缩放因子的尺寸
        padding = int(6 * self.scale_factor)
        btn_padding = f"{padding}px {padding*2}px"
        input_padding = f"{int(8 * self.scale_factor)}px"  # 增加输入框内边距
        group_margin = int(10 * self.scale_factor)
        group_padding = int(10 * self.scale_factor)
        border_style = self.get_border_style()
        border_width = int(1.0 * self.scale_factor)
        
        # 标签页选中与未选中的样式差异
        selected_tab_border = f"border: {int(border_width * 1.5)}px solid {self.get_title_color(index)};"
        unselected_tab_border = f"border: {border_width}px solid {self.get_border_color(index)};"
        
        # 基础样式
        base_style = f"""
            QMainWindow, QWidget {{ 
                background-color: {self.get_bg_color(index)}; 
            }}
            QTabWidget {{
                background-color: {self.get_bg_color(index)};
                color: {self.get_text_color(index)};
            }}
            QTabBar::tab {{
                background-color: {self.get_tab_bg_color(index)};
                color: {self.get_text_color(index)};
                height: {int(32 * self.scale_factor)}px;  /* 增加标签高度 */
                width: {int(120 * self.scale_factor)}px;
                {unselected_tab_border}
                border-bottom: none;
                padding: {int(8 * self.scale_factor)}px;  /* 增加内边距 */
                margin-right: 2px;
                font-weight: normal;
            }}
            QTabBar::tab:selected {{
                background-color: {self.get_group_bg_color(index)};
                {selected_tab_border}
                border-bottom-color: {self.get_group_bg_color(index)};
                font-weight: bold;  /* 选中标签文字加粗 */
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {self.get_hover_color(index)};  /* 未选中标签 hover 效果 */
            }}
            QGroupBox {{
                {border_style}
                border-color: {self.get_border_color(index)};
                margin-top: {group_margin}px;
                padding: {group_padding}px;
                background-color: {self.get_group_bg_color(index)};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: {self.get_title_color(index)};
                font-weight: bold;
            }}
            QPushButton {{
                background-color: {self.get_btn_bg_color(index)};
                color: {self.get_btn_text_color(index)};
                border: none;
                padding: {btn_padding};
                border-radius: {int(4 * self.scale_factor)}px;
            }}
            QPushButton:hover {{ background-color: {self.get_btn_hover_color(index)}; }}
            QPushButton:pressed {{ background-color: {self.get_btn_pressed_color(index)}; }}
            QPushButton:disabled {{
                background-color: {self.get_btn_disabled_color(index)};
                color: {self.get_btn_disabled_text_color(index)};
            }}
            QLineEdit, QTextEdit {{
                padding: {input_padding};
                {border_style}
                border-color: {self.get_input_border_color(index)};
                background-color: {self.get_input_bg_color(index)};
                color: {self.get_text_color(index)};
            }}
            QProgressBar {{
                {border_style}
                border-color: {self.get_border_color(index)};
                text-align: center;
                height: {int(20 * self.scale_factor)}px;
                color: {self.get_text_color(index)};
            }}
            QProgressBar::chunk {{
                background-color: {self.get_progress_color(index)};
                width: 10px;
                margin: 0.5px;
            }}
            QLabel {{ color: {self.get_text_color(index)}; }}
            QComboBox {{
                padding: {input_padding};
                {border_style}
                border-color: {self.get_input_border_color(index)};
                background-color: {self.get_input_bg_color(index)};
                color: {self.get_text_color(index)};
            }}
            /* 移除下拉框图标 */
            QComboBox::down-arrow {{
                width: 0px;
                height: 0px;
            }}
            QComboBox::drop-down {{
                border-left: none;
                width: {int(10 * self.scale_factor)}px;
            }}
            QRadioButton {{
                color: {self.get_text_color(index)};
                margin: {int(5 * self.scale_factor)}px 0;
            }}
            QTabWidget::pane {{
                {border_style}
                border-color: {self.get_border_color(index)};
                background-color: {self.get_group_bg_color(index)};
                margin-top: {int(-1 * self.scale_factor)}px;
            }}
        """
        
        self.setStyleSheet(base_style)
        self.save_settings()
    
    # 标签页悬停颜色
    def get_hover_color(self, index):
        """获取标签页悬停颜色"""
        colors = [
            "#f0f7ff",  # 默认主题
            "#2d2d2d",  # 深色主题
            "#fff0e6",  # 珊瑚橙主题
            "#f0f7f0",  # 橄榄绿主题
            "#e6e6f7",  # 靛蓝色主题
            "#f7f0f7",  # 薰衣草紫主题
            "#e6f7f7",  # 薄荷青主题
            "#fff7e6",  # 琥珀黄主题
            "#f7e6f0",  # 玫瑰粉主题
            "#f0f0f2",  # 石板灰主题
            "#e6f7ef",  # 翡翠绿主题
            "#e6f2f7",  # 天空蓝主题
            "#ffe6e6",  # 夕阳红主题
            "#e6e6f0",  # 深海蓝主题
            "#fff0e0",  # 秋叶橙主题
            "#f0f7e6",  # 嫩芽绿主题
            "#f0e6f7",  # 葡萄紫主题
            "#f7f0e6",  # 沙石棕主题
            "#f7f7f7",  # 冰雪白主题
            "#e6e6e6",  # 墨黑灰主题
            "#f7e6f0",  # 樱花粉主题
            "#e6f2f7"   # 湖水青主题
        ]
        return colors[index]
    
    # 颜色方案配置函数（包含默认主题和深色主题）
    def get_bg_color(self, index):
        """获取背景颜色"""
        colors = [
            "#f8fafc",  # 默认主题 - 清爽浅灰蓝
            "#1e1e1e",  # 深色主题 - 深灰黑色
            "#fff5f0",  # 珊瑚橙主题 - 温暖活力
            "#f9fcf9",  # 橄榄绿主题 - 自然清新
            "#f0f0f7",  # 靛蓝色主题 - 专业沉稳
            "#fcf0fc",  # 薰衣草紫主题 - 优雅浪漫
            "#f0fcfc",  # 薄荷青主题 - 清爽宁静
            "#fff9f0",  # 琥珀黄主题 - 明亮温暖
            "#fcf0f7",  # 玫瑰粉主题 - 柔和甜美
            "#f5f5f7",  # 石板灰主题 - 现代简约
            "#f0fcf7",  # 翡翠绿主题 - 生机活力
            "#f0f7fc",  # 天空蓝主题 - 开阔清爽
            "#fff0f0",  # 夕阳红主题 - 热情温暖
            "#f0f0f9",  # 深海蓝主题 - 沉稳深邃
            "#fff5e6",  # 秋叶橙主题 - 温暖丰富
            "#f7fcf0",  # 嫩芽绿主题 - 清新活力
            "#f9f0fc",  # 葡萄紫主题 - 高贵典雅
            "#fcf5e6",  # 沙石棕主题 - 自然质朴
            "#ffffff",  # 冰雪白主题 - 纯净简约
            "#f0f0f0",  # 墨黑灰主题 - 专业严肃
            "#fef0f7",  # 樱花粉主题 - 柔美浪漫
            "#f0f7fc"   # 湖水青主题 - 平静舒适
        ]
        return colors[index]
    
    def get_group_bg_color(self, index):
        """获取分组背景颜色"""
        colors = [
            "#ffffff",  # 默认主题
            "#2d2d2d",  # 深色主题
            "#ffffff",  # 珊瑚橙主题
            "#ffffff",  # 橄榄绿主题
            "#ffffff",  # 靛蓝色主题
            "#ffffff",  # 薰衣草紫主题
            "#ffffff",  # 薄荷青主题
            "#ffffff",  # 琥珀黄主题
            "#ffffff",  # 玫瑰粉主题
            "#ffffff",  # 石板灰主题
            "#ffffff",  # 翡翠绿主题
            "#ffffff",  # 天空蓝主题
            "#ffffff",  # 夕阳红主题
            "#ffffff",  # 深海蓝主题
            "#ffffff",  # 秋叶橙主题
            "#ffffff",  # 嫩芽绿主题
            "#ffffff",  # 葡萄紫主题
            "#ffffff",  # 沙石棕主题
            "#ffffff",  # 冰雪白主题
            "#ffffff",  # 墨黑灰主题
            "#ffffff",  # 樱花粉主题
            "#ffffff"   # 湖水青主题
        ]
        return colors[index]
    
    def get_tab_bg_color(self, index):
        """获取标签背景颜色"""
        colors = [
            "#f0f7ff",  # 默认主题
            "#1e1e1e",  # 深色主题
            "#fff5f0",  # 珊瑚橙主题
            "#f9fcf9",  # 橄榄绿主题
            "#f0f0f7",  # 靛蓝色主题
            "#fcf0fc",  # 薰衣草紫主题
            "#f0fcfc",  # 薄荷青主题
            "#fff9f0",  # 琥珀黄主题
            "#fcf0f7",  # 玫瑰粉主题
            "#f5f5f7",  # 石板灰主题
            "#f0fcf7",  # 翡翠绿主题
            "#f0f7fc",  # 天空蓝主题
            "#fff0f0",  # 夕阳红主题
            "#f0f0f9",  # 深海蓝主题
            "#fff5e6",  # 秋叶橙主题
            "#f7fcf0",  # 嫩芽绿主题
            "#f9f0fc",  # 葡萄紫主题
            "#fcf5e6",  # 沙石棕主题
            "#ffffff",  # 冰雪白主题
            "#f0f0f0",  # 墨黑灰主题
            "#fef0f7",  # 樱花粉主题
            "#f0f7fc"   # 湖水青主题
        ]
        return colors[index]
    
    def get_text_color(self, index):
        """获取文本颜色"""
        colors = [
            "#2c3e50",  # 默认主题 - 深蓝色文本
            "#e0e0e0",  # 深色主题 - 浅灰色文本
            "#7d4c2f",  # 珊瑚橙主题 - 暖棕色文本
            "#2d5d32",  # 橄榄绿主题 - 深绿色文本
            "#2c3e50",  # 靛蓝色主题 - 深蓝色文本
            "#5b2c6f",  # 薰衣草紫主题 - 深紫色文本
            "#1a7f7f",  # 薄荷青主题 - 深青色文本
            "#805b20",  # 琥珀黄主题 - 深棕色文本
            "#7d3c98",  # 玫瑰粉主题 - 深粉色文本
            "#34495e",  # 石板灰主题 - 深灰色文本
            "#1b7837",  # 翡翠绿主题 - 深绿色文本
            "#1b4f72",  # 天空蓝主题 - 深蓝色文本
            "#8b2323",  # 夕阳红主题 - 深红色文本
            "#1a365d",  # 深海蓝主题 - 深蓝色文本
            "#8b4513",  # 秋叶橙主题 - 棕色文本
            "#2e7d32",  # 嫩芽绿主题 - 深绿色文本
            "#6a1b9a",  # 葡萄紫主题 - 深紫色文本
            "#8d6e63",  # 沙石棕主题 - 棕色文本
            "#212121",  # 冰雪白主题 - 深灰色文本
            "#212121",  # 墨黑灰主题 - 黑色文本
            "#c2185b",  # 樱花粉主题 - 深粉色文本
            "#0d47a1"   # 湖水青主题 - 深蓝色文本
        ]
        return colors[index]
    
    def get_title_color(self, index):
        """获取标题颜色"""
        colors = [
            "#165dff",  # 默认主题 - 蓝色主色调
            "#00a8ff",  # 深色主题 - 亮蓝色主色调
            "#ff7f50",  # 珊瑚橙主题 - 主色调
            "#558b2f",  # 橄榄绿主题 - 主色调
            "#3f51b5",  # 靛蓝色主题 - 主色调
            "#9c27b0",  # 薰衣草紫主题 - 主色调
            "#26a69a",  # 薄荷青主题 - 主色调
            "#ffb300",  # 琥珀黄主题 - 主色调
            "#d81b60",  # 玫瑰粉主题 - 主色调
            "#78909c",  # 石板灰主题 - 主色调
            "#00c853",  # 翡翠绿主题 - 主色调
            "#1976d2",  # 天空蓝主题 - 主色调
            "#e53935",  # 夕阳红主题 - 主色调
            "#1565c0",  # 深海蓝主题 - 主色调
            "#f57c00",  # 秋叶橙主题 - 主色调
            "#66bb6a",  # 嫩芽绿主题 - 主色调
            "#8e24aa",  # 葡萄紫主题 - 主色调
            "#a1887f",  # 沙石棕主题 - 主色调
            "#bdbdbd",  # 冰雪白主题 - 主色调
            "#616161",  # 墨黑灰主题 - 主色调
            "#ec407a",  # 樱花粉主题 - 主色调
            "#42a5f5"   # 湖水青主题 - 主色调
        ]
        return colors[index]
    
    def get_border_color(self, index):
        """获取边框颜色"""
        colors = [
            "#dae8fc",  # 默认主题 - 边框色
            "#4a4a4a",  # 深色主题 - 边框色
            "#ffd7b3",  # 珊瑚橙主题 - 边框色
            "#d6e6d6",  # 橄榄绿主题 - 边框色
            "#d1d1e0",  # 靛蓝色主题 - 边框色
            "#f0ccf0",  # 薰衣草紫主题 - 边框色
            "#ccf0f0",  # 薄荷青主题 - 边框色
            "#ffe6b3",  # 琥珀黄主题 - 边框色
            "#f0ccd9",  # 玫瑰粉主题 - 边框色
            "#d7d7e0",  # 石板灰主题 - 边框色
            "#ccf0e6",  # 翡翠绿主题 - 边框色
            "#cce0f0",  # 天空蓝主题 - 边框色
            "#ffcccc",  # 夕阳红主题 - 边框色
            "#ccd1e0",  # 深海蓝主题 - 边框色
            "#ffddb3",  # 秋叶橙主题 - 边框色
            "#d6f0cc",  # 嫩芽绿主题 - 边框色
            "#e0ccf0",  # 葡萄紫主题 - 边框色
            "#f0e6d6",  # 沙石棕主题 - 边框色
            "#e0e0e0",  # 冰雪白主题 - 边框色
            "#bdbdbd",  # 墨黑灰主题 - 边框色
            "#f0ccd9",  # 樱花粉主题 - 边框色
            "#cce5f0"   # 湖水青主题 - 边框色
        ]
        return colors[index]
    
    def get_input_border_color(self, index):
        """获取输入框边框颜色"""
        colors = [
            "#dae8fc",  # 默认主题
            "#4a4a4a",  # 深色主题
            "#ffd7b3",  # 珊瑚橙主题
            "#d6e6d6",  # 橄榄绿主题
            "#d1d1e0",  # 靛蓝色主题
            "#f0ccf0",  # 薰衣草紫主题
            "#ccf0f0",  # 薄荷青主题
            "#ffe6b3",  # 琥珀黄主题
            "#f0ccd9",  # 玫瑰粉主题
            "#d7d7e0",  # 石板灰主题
            "#ccf0e6",  # 翡翠绿主题
            "#cce0f0",  # 天空蓝主题
            "#ffcccc",  # 夕阳红主题
            "#ccd1e0",  # 深海蓝主题
            "#ffddb3",  # 秋叶橙主题
            "#d6f0cc",  # 嫩芽绿主题
            "#e0ccf0",  # 葡萄紫主题
            "#f0e6d6",  # 沙石棕主题
            "#e0e0e0",  # 冰雪白主题
            "#bdbdbd",  # 墨黑灰主题
            "#f0ccd9",  # 樱花粉主题
            "#cce5f0"   # 湖水青主题
        ]
        return colors[index]
    
    def get_input_bg_color(self, index):
        """获取输入框背景颜色"""
        colors = [
            "#ffffff",  # 默认主题
            "#3a3a3a",  # 深色主题
            "#ffffff",  # 珊瑚橙主题
            "#ffffff",  # 橄榄绿主题
            "#ffffff",  # 靛蓝色主题
            "#ffffff",  # 薰衣草紫主题
            "#ffffff",  # 薄荷青主题
            "#ffffff",  # 琥珀黄主题
            "#ffffff",  # 玫瑰粉主题
            "#ffffff",  # 石板灰主题
            "#ffffff",  # 翡翠绿主题
            "#ffffff",  # 天空蓝主题
            "#ffffff",  # 夕阳红主题
            "#ffffff",  # 深海蓝主题
            "#ffffff",  # 秋叶橙主题
            "#ffffff",  # 嫩芽绿主题
            "#ffffff",  # 葡萄紫主题
            "#ffffff",  # 沙石棕主题
            "#ffffff",  # 冰雪白主题
            "#ffffff",  # 墨黑灰主题
            "#ffffff",  # 樱花粉主题
            "#ffffff"   # 湖水青主题
        ]
        return colors[index]
    
    def get_btn_bg_color(self, index):
        """获取按钮背景颜色"""
        colors = [
            "#165dff",  # 默认主题 - 按钮主色（蓝色）
            "#0078d7",  # 深色主题 - 按钮主色（亮蓝色）
            "#ff7f50",  # 珊瑚橙主题 - 按钮主色
            "#558b2f",  # 橄榄绿主题 - 按钮主色
            "#3f51b5",  # 靛蓝色主题 - 按钮主色
            "#9c27b0",  # 薰衣草紫主题 - 按钮主色
            "#26a69a",  # 薄荷青主题 - 按钮主色
            "#ffb300",  # 琥珀黄主题 - 按钮主色
            "#d81b60",  # 玫瑰粉主题 - 按钮主色
            "#78909c",  # 石板灰主题 - 按钮主色
            "#00c853",  # 翡翠绿主题 - 按钮主色
            "#1976d2",  # 天空蓝主题 - 按钮主色
            "#e53935",  # 夕阳红主题 - 按钮主色
            "#1565c0",  # 深海蓝主题 - 按钮主色
            "#f57c00",  # 秋叶橙主题 - 按钮主色
            "#66bb6a",  # 嫩芽绿主题 - 按钮主色
            "#8e24aa",  # 葡萄紫主题 - 按钮主色
            "#a1887f",  # 沙石棕主题 - 按钮主色
            "#bdbdbd",  # 冰雪白主题 - 按钮主色
            "#616161",  # 墨黑灰主题 - 按钮主色
            "#ec407a",  # 樱花粉主题 - 按钮主色
            "#42a5f5"   # 湖水青主题 - 按钮主色
        ]
        return colors[index]
    
    def get_btn_text_color(self, index):
        """获取按钮文本颜色"""
        colors = [
            "#ffffff",  # 默认主题 - 白色文字
            "#ffffff",  # 深色主题 - 白色文字
            "#ffffff",  # 珊瑚橙主题 - 白色文字
            "#ffffff",  # 橄榄绿主题 - 白色文字
            "#ffffff",  # 靛蓝色主题 - 白色文字
            "#ffffff",  # 薰衣草紫主题 - 白色文字
            "#ffffff",  # 薄荷青主题 - 白色文字
            "#ffffff",  # 琥珀黄主题 - 白色文字
            "#ffffff",  # 玫瑰粉主题 - 白色文字
            "#ffffff",  # 石板灰主题 - 白色文字
            "#ffffff",  # 翡翠绿主题 - 白色文字
            "#ffffff",  # 天空蓝主题 - 白色文字
            "#ffffff",  # 夕阳红主题 - 白色文字
            "#ffffff",  # 深海蓝主题 - 白色文字
            "#ffffff",  # 秋叶橙主题 - 白色文字
            "#ffffff",  # 嫩芽绿主题 - 白色文字
            "#ffffff",  # 葡萄紫主题 - 白色文字
            "#ffffff",  # 沙石棕主题 - 白色文字
            "#ffffff",  # 冰雪白主题 - 白色文字
            "#ffffff",  # 墨黑灰主题 - 白色文字
            "#ffffff",  # 樱花粉主题 - 白色文字
            "#ffffff"   # 湖水青主题 - 白色文字
        ]
        return colors[index]
    
    def get_btn_hover_color(self, index):
        """获取按钮悬停颜色"""
        colors = [
            "#0e42c3",  # 默认主题 - 按钮深色
            "#005a9e",  # 深色主题 - 按钮深色
            "#ff6347",  # 珊瑚橙主题 - 按钮深色
            "#4a7a28",  # 橄榄绿主题 - 按钮深色
            "#303f9f",  # 靛蓝色主题 - 按钮深色
            "#8e24aa",  # 薰衣草紫主题 - 按钮深色
            "#00897b",  # 薄荷青主题 - 按钮深色
            "#ffa000",  # 琥珀黄主题 - 按钮深色
            "#c2185b",  # 玫瑰粉主题 - 按钮深色
            "#607d8b",  # 石板灰主题 - 按钮深色
            "#00b248",  # 翡翠绿主题 - 按钮深色
            "#0d47a1",  # 天空蓝主题 - 按钮深色
            "#c62828",  # 夕阳红主题 - 按钮深色
            "#0d47a1",  # 深海蓝主题 - 按钮深色
            "#e65100",  # 秋叶橙主题 - 按钮深色
            "#43a047",  # 嫩芽绿主题 - 按钮深色
            "#7b1fa2",  # 葡萄紫主题 - 按钮深色
            "#8d6e63",  # 沙石棕主题 - 按钮深色
            "#9e9e9e",  # 冰雪白主题 - 按钮深色
            "#424242",  # 墨黑灰主题 - 按钮深色
            "#c2185b",  # 樱花粉主题 - 按钮深色
            "#1e88e5"   # 湖水青主题 - 按钮深色
        ]
        return colors[index]
    
    def get_btn_pressed_color(self, index):
        """获取按钮按下颜色"""
        colors = [
            "#0a3491",  # 默认主题 - 按钮更深色
            "#004a80",  # 深色主题 - 按钮更深色
            "#e65c3d",  # 珊瑚橙主题 - 按钮更深色
            "#3d6920",  # 橄榄绿主题 - 按钮更深色
            "#283593",  # 靛蓝色主题 - 按钮更深色
            "#7b1fa2",  # 薰衣草紫主题 - 按钮更深色
            "#00695c",  # 薄荷青主题 - 按钮更深色
            "#e69100",  # 琥珀黄主题 - 按钮更深色
            "#ad1457",  # 玫瑰粉主题 - 按钮更深色
            "#546e7a",  # 石板灰主题 - 按钮更深色
            "#009624",  # 翡翠绿主题 - 按钮更深色
            "#0d47a1",  # 天空蓝主题 - 按钮更深色
            "#b71c1c",  # 夕阳红主题 - 按钮更深色
            "#0d47a1",  # 深海蓝主题 - 按钮更深色
            "#d32f2f",  # 秋叶橙主题 - 按钮更深色
            "#388e3c",  # 嫩芽绿主题 - 按钮更深色
            "#6a1b9a",  # 葡萄紫主题 - 按钮更深色
            "#795548",  # 沙石棕主题 - 按钮更深色
            "#757575",  # 冰雪白主题 - 按钮更深色
            "#212121",  # 墨黑灰主题 - 按钮更深色
            "#ad1457",  # 樱花粉主题 - 按钮更深色
            "#1565c0"   # 湖水青主题 - 按钮更深色
        ]
        return colors[index]
    
    def get_btn_disabled_color(self, index):
        """获取按钮禁用颜色"""
        colors = [
            "#b8d0fc",  # 默认主题 - 按钮浅色
            "#4c6b8a",  # 深色主题 - 按钮浅色
            "#ffd7b3",  # 珊瑚橙主题 - 按钮浅色
            "#d6e6d6",  # 橄榄绿主题 - 按钮浅色
            "#d1d1e0",  # 靛蓝色主题 - 按钮浅色
            "#f0ccf0",  # 薰衣草紫主题 - 按钮浅色
            "#ccf0f0",  # 薄荷青主题 - 按钮浅色
            "#ffe6b3",  # 琥珀黄主题 - 按钮浅色
            "#f0ccd9",  # 玫瑰粉主题 - 按钮浅色
            "#d7d7e0",  # 石板灰主题 - 按钮浅色
            "#ccf0e6",  # 翡翠绿主题 - 按钮浅色
            "#cce0f0",  # 天空蓝主题 - 按钮浅色
            "#ffcccc",  # 夕阳红主题 - 按钮浅色
            "#ccd1e0",  # 深海蓝主题 - 按钮浅色
            "#ffddb3",  # 秋叶橙主题 - 按钮浅色
            "#d6f0cc",  # 嫩芽绿主题 - 按钮浅色
            "#e0ccf0",  # 葡萄紫主题 - 按钮浅色
            "#f0e6d6",  # 沙石棕主题 - 按钮浅色
            "#e0e0e0",  # 冰雪白主题 - 按钮浅色
            "#bdbdbd",  # 墨黑灰主题 - 按钮浅色
            "#f0ccd9",  # 樱花粉主题 - 按钮浅色
            "#cce5f0"   # 湖水青主题 - 按钮浅色
        ]
        return colors[index]
    
    def get_btn_disabled_text_color(self, index):
        """获取按钮禁用文本颜色"""
        colors = [
            "#e0e0e0",  # 默认主题 - 禁用文字色
            "#999999",  # 深色主题 - 禁用文字色
            "#cc9966",  # 珊瑚橙主题 - 禁用文字色
            "#88aa88",  # 橄榄绿主题 - 禁用文字色
            "#9999b3",  # 靛蓝色主题 - 禁用文字色
            "#cc99cc",  # 薰衣草紫主题 - 禁用文字色
            "#88bbbb",  # 薄荷青主题 - 禁用文字色
            "#cca666",  # 琥珀黄主题 - 禁用文字色
            "#cc99b3",  # 玫瑰粉主题 - 禁用文字色
            "#99a3b3",  # 石板灰主题 - 禁用文字色
            "#88ccaa",  # 翡翠绿主题 - 禁用文字色
            "#88aadd",  # 天空蓝主题 - 禁用文字色
            "#cc8888",  # 夕阳红主题 - 禁用文字色
            "#8899cc",  # 深海蓝主题 - 禁用文字色
            "#cc9966",  # 秋叶橙主题 - 禁用文字色
            "#88cc88",  # 嫩芽绿主题 - 禁用文字色
            "#aa88cc",  # 葡萄紫主题 - 禁用文字色
            "#ccb399",  # 沙石棕主题 - 禁用文字色
            "#bbbbbb",  # 冰雪白主题 - 禁用文字色
            "#999999",  # 墨黑灰主题 - 禁用文字色
            "#cc99b3",  # 樱花粉主题 - 禁用文字色
            "#88bbee"   # 湖水青主题 - 禁用文字色
        ]
        return colors[index]
    
    def get_progress_color(self, index):
        """获取进度条颜色"""
        colors = [
            "#165dff",  # 默认主题 - 进度条色
            "#00a8ff",  # 深色主题 - 进度条色
            "#ff7f50",  # 珊瑚橙主题 - 进度条色
            "#558b2f",  # 橄榄绿主题 - 进度条色
            "#3f51b5",  # 靛蓝色主题 - 进度条色
            "#9c27b0",  # 薰衣草紫主题 - 进度条色
            "#26a69a",  # 薄荷青主题 - 进度条色
            "#ffb300",  # 琥珀黄主题 - 进度条色
            "#d81b60",  # 玫瑰粉主题 - 进度条色
            "#78909c",  # 石板灰主题 - 进度条色
            "#00c853",  # 翡翠绿主题 - 进度条色
            "#1976d2",  # 天空蓝主题 - 进度条色
            "#e53935",  # 夕阳红主题 - 进度条色
            "#1565c0",  # 深海蓝主题 - 进度条色
            "#f57c00",  # 秋叶橙主题 - 进度条色
            "#66bb6a",  # 嫩芽绿主题 - 进度条色
            "#8e24aa",  # 葡萄紫主题 - 进度条色
            "#a1887f",  # 沙石棕主题 - 进度条色
            "#bdbdbd",  # 冰雪白主题 - 进度条色
            "#616161",  # 墨黑灰主题 - 进度条色
            "#ec407a",  # 樱花粉主题 - 进度条色
            "#42a5f5"   # 湖水青主题 - 进度条色
        ]
        return colors[index]
    
    def load_saved_paths(self):
        """加载保存的路径"""
        sources = self.settings.value("source_paths", [])
        dests = self.settings.value("dest_paths", [])
        
        if sources:
            self.common_source_combo.addItems(sources)
        if dests:
            self.common_dest_combo.addItems(dests)
    
    def save_current_paths(self):
        """保存当前地址到常用地址"""
        source_path = self.source_edit.text()
        dest_path = self.dest_edit.text()
        
        if source_path and os.path.isdir(source_path):
            sources = [self.common_source_combo.itemText(i) for i in range(self.common_source_combo.count())]
            if source_path not in sources:
                self.common_source_combo.addItem(source_path)
                sources.append(source_path)
                self.settings.setValue("source_paths", sources)
        
        if dest_path and os.path.isdir(dest_path):
            dests = [self.common_dest_combo.itemText(i) for i in range(self.common_dest_combo.count())]
            if dest_path not in dests:
                self.common_dest_combo.addItem(dest_path)
                dests.append(dest_path)
                self.settings.setValue("dest_paths", dests)
        
        self.log("已保存当前地址到常用地址")
    
    def on_source_changed(self, index):
        """源地址下拉框变化时更新输入框"""
        if index >= 0:
            self.source_edit.setText(self.common_source_combo.currentText())
    
    def on_dest_changed(self, index):
        """目标地址下拉框变化时更新输入框"""
        if index >= 0:
            self.dest_edit.setText(self.common_dest_combo.currentText())
    
    def select_source_folder(self):
        """选择源文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择源文件夹")
        if folder:
            self.source_edit.setText(folder)
    
    def select_dest_folder(self):
        """选择目标文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择目标文件夹")
        if folder:
            self.dest_edit.setText(folder)
    
    def start_organizing(self):
        """开始整理文件"""
        source_folder = self.source_edit.text()
        dest_folder = self.dest_edit.text()
        
        # 获取文件类型筛选
        file_type_index = self.file_type_combo.currentIndex()
        file_type_filter = "all"  # 默认所有类型
        custom_extensions = []
        
        if file_type_index == 1:
            file_type_filter = "images"
        elif file_type_index == 2:
            file_type_filter = "videos"
        elif file_type_index == 3:
            file_type_filter = "lrv"
        elif file_type_index == 4:
            file_type_filter = "custom"
            # 处理自定义扩展名
            custom_input = self.custom_extensions_edit.text().strip()
            if not custom_input:
                self.log("请输入自定义文件格式")
                QMessageBox.warning(self, "错误", "请输入自定义文件格式，用逗号分隔（例如: .txt,.pdf）")
                return
            # 处理输入，确保每个扩展名以.开头
            custom_extensions = [ext.strip() if ext.strip().startswith('.') else f'.{ext.strip()}' 
                               for ext in custom_input.split(',') if ext.strip()]
            if not custom_extensions:
                self.log("无效的自定义文件格式")
                QMessageBox.warning(self, "错误", "无效的自定义文件格式，请检查输入")
                return
        
        # 获取同名文件处理方式
        duplicate_handling = self.duplicate_button_group.checkedId()
        if duplicate_handling == -1:  # 没有选择时默认重命名
            duplicate_handling = 1
        
        if not source_folder or not os.path.isdir(source_folder):
            self.log("请选择有效的源文件夹")
            QMessageBox.warning(self, "错误", "请选择有效的源文件夹")
            return
        
        if not dest_folder or not os.path.isdir(dest_folder):
            self.log("请选择有效的目标文件夹")
            QMessageBox.warning(self, "错误", "请选择有效的目标文件夹")
            return
        
        # 获取所有符合条件的文件
        try:
            # 先获取所有文件
            all_files = [f for f in os.listdir(source_folder) 
                        if os.path.isfile(os.path.join(source_folder, f))]
            
            # 筛选符合条件的文件
            file_list = []
            for filename in all_files:
                filename_lower = filename.lower()
                
                # 图片文件
                image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.raw')
                # 视频文件
                video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.mpeg', '.mpg', '.3gp')
                # LRV文件
                lrv_extension = '.lrv'
                
                # 检查是否符合筛选条件
                if file_type_filter == "all" or file_type_filter == "images":
                    if filename_lower.endswith(image_extensions):
                        file_list.append(filename)
                        continue
                        
                if file_type_filter == "all" or file_type_filter == "videos":
                    if filename_lower.endswith(video_extensions):
                        file_list.append(filename)
                        continue
                        
                if file_type_filter == "all" or file_type_filter == "lrv":
                    if filename_lower.endswith(lrv_extension):
                        file_list.append(filename)
                        continue
                        
                if file_type_filter == "custom":
                    if any(filename_lower.endswith(ext.lower()) for ext in custom_extensions):
                        file_list.append(filename)
                        continue
            
            if not file_list:
                self.log("源文件夹中没有找到符合条件的文件")
                QMessageBox.information(self, "提示", "源文件夹中没有找到符合条件的文件")
                return
            
            self.log(f"找到 {len(file_list)} 个符合条件的文件，开始整理...")
            # 记录同名文件处理方式
            handling_text = "自动重命名" if duplicate_handling == 1 else "覆盖现有文件" if duplicate_handling == 2 else "跳过同名文件"
            self.log(f"同名文件处理方式: {handling_text}")
            
            # 禁用开始按钮，启用其他控制按钮
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.source_btn.setEnabled(False)
            self.dest_btn.setEnabled(False)
            self.save_paths_btn.setEnabled(False)
            self.file_type_combo.setEnabled(False)
            self.custom_extensions_edit.setEnabled(False)
            self.rename_radio.setEnabled(False)
            self.overwrite_radio.setEnabled(False)
            self.skip_radio.setEnabled(False)
            
            # 创建并启动传输线程
            self.transfer_thread = FileTransferThread(
                source_folder, dest_folder, file_list, file_type_filter, 
                custom_extensions, duplicate_handling
            )
            self.transfer_thread.progress_updated.connect(self.update_progress)
            self.transfer_thread.log_updated.connect(self.log)
            self.transfer_thread.transfer_complete.connect(self.transfer_finished)
            self.transfer_thread.speed_updated.connect(self.update_speed)
            self.transfer_thread.file_count_updated.connect(self.update_file_count)
            self.transfer_thread.start()
            
            self.status_label.setText("正在整理...")
            
        except Exception as e:
            self.log(f"发生错误: {str(e)}")
            QMessageBox.critical(self, "错误", f"发生错误: {str(e)}")
    
    def pause_organizing(self):
        """暂停整理"""
        if self.transfer_thread and self.transfer_thread.isRunning():
            self.transfer_thread.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.status_label.setText("已暂停")
            self.log("操作已暂停")
    
    def resume_organizing(self):
        """继续整理"""
        if self.transfer_thread and self.transfer_thread.isRunning():
            self.transfer_thread.resume()
            self.resume_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.status_label.setText("正在整理...")
            self.log("操作已继续")
    
    def stop_organizing(self):
        """停止整理"""
        if self.transfer_thread and (self.transfer_thread.isRunning() or self.transfer_thread.paused):
            self.transfer_thread.stop()
            self.reset_controls()
            self.status_label.setText("已停止")
    
    def transfer_finished(self):
        """传输完成时调用"""
        self.reset_controls()
        self.status_label.setText("整理完成")
        self.speed_label.setText("速度: --")
        self.log("文件整理完成")
        QMessageBox.information(self, "完成", "文件整理已完成")
    
    def reset_controls(self):
        """重置控制按钮状态"""
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.source_btn.setEnabled(True)
        self.dest_btn.setEnabled(True)
        self.save_paths_btn.setEnabled(True)
        self.file_type_combo.setEnabled(True)
        self.rename_radio.setEnabled(True)
        self.overwrite_radio.setEnabled(True)
        self.skip_radio.setEnabled(True)
        # 根据当前选择决定是否启用自定义格式输入框
        self.custom_extensions_edit.setEnabled(self.file_type_combo.currentIndex() == 4)
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
    
    def update_file_count(self, current, total):
        """更新文件计数显示"""
        self.file_count_label.setText(f"文件: {current}/{total}")
    
    def update_speed(self, speed_text):
        """更新速度显示"""
        self.speed_label.setText(f"速度: {speed_text}")
    
    def log(self, message):
        """添加日志信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        # 更新状态栏
        self.statusBar().showMessage(message)

# 程序入口，添加启动画面逻辑
def main():
    import sys
    app = QApplication(sys.argv)
    
    # 确保中文显示正常
    font = QFont("SimHei")
    app.setFont(font)
    
    # 创建并显示启动画面
    script_dir = os.path.dirname(os.path.abspath(__file__))
    splash_image_path = os.path.join(script_dir, "splash.png")  # 启动图片路径
    
    # 检查图片文件是否存在
    if os.path.exists(splash_image_path):
        splash_pix = QPixmap(splash_image_path)
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)  # 无边框且置顶
        splash.setEnabled(False)  # 不可操作
        splash.show()
        
        # 处理事件以确保启动画面显示
        app.processEvents()
        
        # 显示3秒
        QTimer.singleShot(3000, splash.close)
    else:
        print(f"警告: 未找到启动图片 {splash_image_path}，将直接启动程序")
    
    # 创建并显示主窗口
    window = MediaOrganizer()
    
    # 如果显示了启动画面，在其关闭后显示主窗口
    if 'splash' in locals():
        QTimer.singleShot(3000, window.show)
    else:
        window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()