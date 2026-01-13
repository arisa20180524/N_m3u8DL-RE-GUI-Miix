import sys
import os
import subprocess
import threading
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QFileDialog, QCheckBox, QTextEdit, QGroupBox, QGridLayout, QSpinBox,
    QProgressBar, QMessageBox, QComboBox, QTabWidget, QScrollArea, QSizePolicy,
    QFrame, QSplitter, QToolButton
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor

class DownloadThread(QThread):
    """专门的下载线程类"""
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    download_complete = pyqtSignal(int)  # 添加退出代码参数
    command_ready = pyqtSignal(str)  # 发送构建的命令
    
    def __init__(self, cmd, work_dir, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.work_dir = work_dir
        self.process = None
        self.is_running = True
        
    def run(self):
        try:
            self.update_log.emit(f"执行命令：{' '.join(self.cmd)}")
            self.command_ready.emit(' '.join(self.cmd))
            
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=self.work_dir,
                encoding='utf-8',
                errors='replace'
            )
            
            for line in iter(self.process.stdout.readline, ''):
                if not self.is_running:
                    break
                if line.strip():
                    self.update_log.emit(line.strip())
                    
                    # 改进的进度解析逻辑
                    if "%" in line:
                        try:
                            parts = line.split()
                            for part in parts:
                                if "%" in part and part.replace('%', '').replace('.', '').isdigit():
                                    progress = float(part.replace('%', ''))
                                    self.update_progress.emit(int(progress))
                                    break
                        except Exception as e:
                            pass
            
            if self.is_running:
                exit_code = self.process.wait()
                self.download_complete.emit(exit_code)
            else:
                # 用户中断，强制终止进程
                if self.process:
                    try:
                        self.process.terminate()
                        self.process.wait(timeout=3)
                    except:
                        pass
                    finally:
                        self.download_complete.emit(-1)
                        
        except Exception as e:
            self.update_log.emit(f"下载线程错误：{str(e)}")
            self.download_complete.emit(-2)
            
    def stop(self):
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
            except:
                pass

class M3U8Downloader(QMainWindow):
    # 自定义信号
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    download_complete = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        # 绑定信号
        self.update_progress.connect(self.on_update_progress)
        self.update_log.connect(self.on_update_log)
        self.download_complete.connect(self.on_download_complete)
        # 下载线程
        self.download_thread = None
        # 窗口置顶状态
        self.is_always_on_top = False
        # 加载上次设置
        self.load_last_settings()
    
    def init_ui(self):
        # 设置窗口标题和图标
        self.setWindowTitle('N_m3u8DL-RE GUI Miix')
        try:
            self.setWindowIcon(QIcon("favicon.ico"))
        except:
            pass
        
        # 获取屏幕尺寸
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        # 设置窗口大小
        window_width = int(screen_geometry.width() * 0.6)
        window_height = int(screen_geometry.height() * 0.97)
        self.setGeometry(100, 100, window_width, window_height)
        
        # 居中显示
        x = (screen_geometry.width() - window_width) // 2
        y = (screen_geometry.height() - window_height) // 2
        self.move(x, y)
        
        self.setMinimumSize(1000, 750)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # 顶部按钮栏
        top_button_layout = QHBoxLayout()
        top_button_layout.setSpacing(10)
        
        # 图钉按钮
        self.pin_btn = QToolButton()
        self.pin_btn.setText("📌")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip("窗口置顶")
        self.pin_btn.setMinimumSize(35, 35)
        self.pin_btn.setStyleSheet("""
            QToolButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 14px;
                qproperty-iconSize: 16px;
            }
            QToolButton:checked {
                background-color: #ffb8c6;
                border: 1px solid #ffa0b2;
            }
            QToolButton:hover {
                background-color: #e8e8e8;
            }
        """)
        self.pin_btn.clicked.connect(self.toggle_pin_window)
        top_button_layout.addWidget(self.pin_btn)
        
        # 添加清空日志按钮
        clear_log_btn = QPushButton("🗑️ 清空日志")
        clear_log_btn.setMinimumHeight(35)
        clear_log_btn.setMinimumWidth(100)
        clear_log_btn.clicked.connect(self.clear_log)
        clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                color: #333333;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 12px;
                border: 1px solid #cccccc;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
                border: 1px solid #aaaaaa;
            }
        """)
        top_button_layout.addWidget(clear_log_btn)
        
        top_button_layout.addStretch()
        
        # 保存设置按钮
        save_btn = QPushButton("💾 保存设置")
        save_btn.setMinimumHeight(35)
        save_btn.setMinimumWidth(120)
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
                border: 1px solid #555555;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #444444;
                border: 1px solid #666666;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)
        top_button_layout.addWidget(save_btn)
        
        # 加载设置按钮
        load_btn = QPushButton("📂 加载设置")
        load_btn.setMinimumHeight(35)
        load_btn.setMinimumWidth(120)
        load_btn.clicked.connect(self.load_settings)
        load_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
                border: 1px solid #555555;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #444444;
                border: 1px solid #666666;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)
        top_button_layout.addWidget(load_btn)
        
        main_layout.addLayout(top_button_layout)
        
        # 创建标签页容器
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabPosition(QTabWidget.North)
        
        # 基础设置标签页
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setSpacing(10)
        
        # 路径设置组
        path_group = QGroupBox("路径设置")
        path_layout = QGridLayout()
        path_layout.setSpacing(8)
        
        # 第一行：执行程序
        path_layout.addWidget(QLabel("执行程序："), 0, 0)
        self.executable_edit = QLineEdit()
        self.executable_edit.setText("N_m3u8DL-RE.exe")
        self.executable_edit.setMinimumHeight(32)
        path_layout.addWidget(self.executable_edit, 0, 1)
        
        browse_btn = QPushButton("选择")
        browse_btn.clicked.connect(self.browse_executable)
        browse_btn.setMinimumWidth(70)
        browse_btn.setMaximumWidth(70)
        browse_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        path_layout.addWidget(browse_btn, 0, 2)
        
        # 第二行：工作目录
        path_layout.addWidget(QLabel("工作目录："), 1, 0)
        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setMinimumHeight(32)
        path_layout.addWidget(self.work_dir_edit, 1, 1)
        
        dir_btn = QPushButton("选择")
        dir_btn.clicked.connect(self.browse_work_dir)
        dir_btn.setMinimumWidth(70)
        dir_btn.setMaximumWidth(70)
        dir_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        path_layout.addWidget(dir_btn, 1, 2)
        
        # 第三行：FFmpeg路径
        path_layout.addWidget(QLabel("FFmpeg路径："), 2, 0)
        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_edit.setPlaceholderText("选择FFmpeg可执行文件路径")
        self.ffmpeg_path_edit.setMinimumHeight(32)
        path_layout.addWidget(self.ffmpeg_path_edit, 2, 1)
        
        ffmpeg_browse_btn = QPushButton("选择")
        ffmpeg_browse_btn.clicked.connect(self.browse_ffmpeg_path)
        ffmpeg_browse_btn.setMinimumWidth(70)
        ffmpeg_browse_btn.setMaximumWidth(70)
        ffmpeg_browse_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        path_layout.addWidget(ffmpeg_browse_btn, 2, 2)
        
        path_group.setLayout(path_layout)
        basic_layout.addWidget(path_group)
        
        # 下载设置组
        url_group = QGroupBox("下载设置")
        url_layout = QGridLayout()
        url_layout.setSpacing(8)
        
        url_layout.addWidget(QLabel("M3U8地址："), 0, 0)
        self.m3u8_url_edit = QLineEdit()
        self.m3u8_url_edit.setPlaceholderText("输入M3U8地址，支持HTTP/HTTPS协议")
        self.m3u8_url_edit.setMinimumHeight(32)
        url_layout.addWidget(self.m3u8_url_edit, 0, 1, 1, 3)
        
        url_layout.addWidget(QLabel("视频标题："), 1, 0)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("输入视频标题，将作为文件名")
        self.title_edit.setMinimumHeight(32)
        url_layout.addWidget(self.title_edit, 1, 1)
        
        url_layout.addWidget(QLabel("请求头："), 1, 2)
        self.headers_edit = QLineEdit()
        self.headers_edit.setPlaceholderText("格式: Header1:Value1")
        self.headers_edit.setMinimumHeight(32)
        url_layout.addWidget(self.headers_edit, 1, 3)
        
        url_layout.addWidget(QLabel("BASEURL："), 2, 0)
        self.baseurl_edit = QLineEdit()
        self.baseurl_edit.setPlaceholderText("设置基础URL，用于相对路径解析")
        self.baseurl_edit.setMinimumHeight(32)
        url_layout.addWidget(self.baseurl_edit, 2, 1)
        
        url_layout.addWidget(QLabel("混流文件："), 2, 2)
        self.mux_file_edit = QLineEdit()
        self.mux_file_edit.setPlaceholderText("选择要混流的本地文件")
        self.mux_file_edit.setMinimumHeight(32)
        url_layout.addWidget(self.mux_file_edit, 2, 3)
        
        mux_btn = QPushButton("选择")
        mux_btn.clicked.connect(self.browse_mux_file)
        mux_btn.setMinimumWidth(70)
        mux_btn.setMaximumWidth(70)
        mux_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        url_layout.addWidget(mux_btn, 2, 4)
        
        url_group.setLayout(url_layout)
        basic_layout.addWidget(url_group)
        
        # 范围选择和性能设置
        top_row_layout = QHBoxLayout()
        top_row_layout.setSpacing(10)
        
        # 范围选择
        range_group = QGroupBox("范围选择")
        range_layout = QHBoxLayout()
        range_layout.setSpacing(8)
        
        range_layout.addWidget(QLabel("开始时间："))
        self.start_time_edit = QLineEdit("00:00:00")
        self.start_time_edit.setMinimumHeight(32)
        self.start_time_edit.setMaximumWidth(90)
        range_layout.addWidget(self.start_time_edit)
        
        range_layout.addWidget(QLabel("结束时间："))
        self.end_time_edit = QLineEdit("00:00:00")
        self.end_time_edit.setMinimumHeight(32)
        self.end_time_edit.setMaximumWidth(90)
        range_layout.addWidget(self.end_time_edit)
        
        range_group.setLayout(range_layout)
        top_row_layout.addWidget(range_group, 1)
        
        # 性能设置
        performance_group = QGroupBox("性能设置")
        performance_layout = QHBoxLayout()
        performance_layout.setSpacing(10)
        
        # 下载线程数
        threads_layout = QHBoxLayout()
        threads_layout.addWidget(QLabel("线程数："))
        self.max_threads = QSpinBox()
        self.max_threads.setRange(1, 100)
        self.max_threads.setValue(32)
        self.max_threads.setMinimumHeight(32)
        self.max_threads.setMaximumWidth(70)
        threads_layout.addWidget(self.max_threads)
        performance_layout.addLayout(threads_layout)
        
        # 重试次数
        retry_layout = QHBoxLayout()
        retry_layout.addWidget(QLabel("重试："))
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 100)
        self.retry_count.setValue(15)
        self.retry_count.setMinimumHeight(32)
        self.retry_count.setMaximumWidth(70)
        retry_layout.addWidget(self.retry_count)
        performance_layout.addLayout(retry_layout)
        
        # HTTP超时
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("超时："))
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 300)
        self.timeout.setValue(100)
        self.timeout.setMinimumHeight(32)
        self.timeout.setMaximumWidth(70)
        timeout_layout.addWidget(self.timeout)
        performance_layout.addLayout(timeout_layout)
        
        # 限速
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("限速："))
        self.limit_speed = QSpinBox()
        self.limit_speed.setRange(0, 10000)
        self.limit_speed.setValue(0)
        self.limit_speed.setMinimumHeight(32)
        self.limit_speed.setMaximumWidth(90)
        speed_layout.addWidget(self.limit_speed)
        speed_layout.addWidget(QLabel("kb/s"))
        performance_layout.addLayout(speed_layout)
        
        performance_group.setLayout(performance_layout)
        top_row_layout.addWidget(performance_group, 2)
        
        basic_layout.addLayout(top_row_layout)
        
        # 基础选项
        options_group = QGroupBox("基础选项")
        options_layout = QGridLayout()
        options_layout.setSpacing(8)
        options_layout.setHorizontalSpacing(15)
        
        # 第一行
        self.del_after_merge = QCheckBox("合并后删除分片")
        self.del_after_merge.setChecked(True)
        options_layout.addWidget(self.del_after_merge, 0, 0)
        
        self.only_parse_m3u8 = QCheckBox("仅解析m3u8")
        options_layout.addWidget(self.only_parse_m3u8, 0, 1)
        
        self.mux_while_download = QCheckBox("混流MP4边下边看")
        options_layout.addWidget(self.mux_while_download, 0, 2)
        
        self.binary_merge = QCheckBox("使用二进制合并")
        options_layout.addWidget(self.binary_merge, 0, 3)
        
        # 第二行
        self.auto_select = QCheckBox("自动选择最佳轨道")
        self.auto_select.setChecked(True)
        options_layout.addWidget(self.auto_select, 1, 0)
        
        self.check_segments_count = QCheckBox("检测分片数量")
        self.check_segments_count.setChecked(True)
        options_layout.addWidget(self.check_segments_count, 1, 1)
        
        self.concurrent_download = QCheckBox("并发下载音视频")
        self.concurrent_download.setChecked(True)
        options_layout.addWidget(self.concurrent_download, 1, 2)
        
        self.merge_to_mp4 = QCheckBox("合并为mp4")
        self.merge_to_mp4.setChecked(True)
        self.merge_to_mp4.setToolTip("如果勾选，将在命令中添加 -M format=mp4 参数")
        options_layout.addWidget(self.merge_to_mp4, 1, 3)
        
        options_group.setLayout(options_layout)
        basic_layout.addWidget(options_group)
        
        # 自定义参数和解密密钥
        custom_args_group = QGroupBox("高级参数")
        custom_args_layout = QGridLayout()
        custom_args_layout.setSpacing(8)
        
        custom_args_layout.addWidget(QLabel("自定义参数："), 0, 0)
        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("输入其他自定义命令行参数，用空格分隔")
        self.args_edit.setMinimumHeight(32)
        custom_args_layout.addWidget(self.args_edit, 0, 1)
        
        custom_args_layout.addWidget(QLabel("解密密钥："), 0, 2)
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("格式: KID1:KEY1 或直接输入KEY")
        self.key_edit.setMinimumHeight(32)
        custom_args_layout.addWidget(self.key_edit, 0, 3)
        
        custom_args_group.setLayout(custom_args_layout)
        basic_layout.addWidget(custom_args_group)
        
        # 添加弹性空间
        basic_layout.addStretch()
        
        # 将基础标签页添加到标签页容器
        self.tab_widget.addTab(basic_tab, "基础设置")
        
        # 高级设置标签页
        advanced_tab = QWidget()
        advanced_scroll = QScrollArea()
        advanced_scroll.setWidgetResizable(True)
        advanced_scroll.setWidget(advanced_tab)
        
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setSpacing(12)
        
        # 输出设置
        output_group = QGroupBox("输出设置")
        output_layout = QGridLayout()
        output_layout.setSpacing(8)
        
        # 临时目录
        output_layout.addWidget(QLabel("临时目录："), 0, 0)
        self.tmp_dir_edit = QLineEdit()
        self.tmp_dir_edit.setPlaceholderText("设置临时文件存储目录")
        self.tmp_dir_edit.setMinimumHeight(32)
        output_layout.addWidget(self.tmp_dir_edit, 0, 1, 1, 2)
        
        tmp_dir_btn = QPushButton("选择")
        tmp_dir_btn.clicked.connect(lambda: self.browse_directory(self.tmp_dir_edit))
        tmp_dir_btn.setMinimumWidth(70)
        tmp_dir_btn.setMaximumWidth(70)
        tmp_dir_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        output_layout.addWidget(tmp_dir_btn, 0, 3)
        
        # 文件命名模板
        output_layout.addWidget(QLabel("文件命名模板："), 1, 0)
        self.save_pattern_edit = QLineEdit()
        self.save_pattern_edit.setPlaceholderText("如: <SaveName>_<Resolution>_<Bandwidth>")
        self.save_pattern_edit.setMinimumHeight(32)
        output_layout.addWidget(self.save_pattern_edit, 1, 1, 1, 3)
        
        # 日志文件路径
        output_layout.addWidget(QLabel("日志文件路径："), 2, 0)
        self.log_file_path_edit = QLineEdit()
        self.log_file_path_edit.setPlaceholderText("如: C:\\Logs\\log.txt")
        self.log_file_path_edit.setMinimumHeight(32)
        output_layout.addWidget(self.log_file_path_edit, 2, 1, 1, 2)
        
        log_file_btn = QPushButton("选择")
        log_file_btn.clicked.connect(lambda: self.browse_file(self.log_file_path_edit, "日志文件 (*.txt)"))
        log_file_btn.setMinimumWidth(70)
        log_file_btn.setMaximumWidth(70)
        log_file_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        output_layout.addWidget(log_file_btn, 2, 3)
        
        # 密钥文本文件
        output_layout.addWidget(QLabel("密钥文本文件："), 3, 0)
        self.key_text_file_edit = QLineEdit()
        self.key_text_file_edit.setPlaceholderText("设置密钥文件")
        self.key_text_file_edit.setMinimumHeight(32)
        output_layout.addWidget(self.key_text_file_edit, 3, 1, 1, 2)
        
        key_file_btn = QPushButton("选择")
        key_file_btn.clicked.connect(lambda: self.browse_file(self.key_text_file_edit, "文本文件 (*.txt)"))
        key_file_btn.setMinimumWidth(70)
        key_file_btn.setMaximumWidth(70)
        key_file_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        output_layout.addWidget(key_file_btn, 3, 3)
        
        output_group.setLayout(output_layout)
        advanced_layout.addWidget(output_group)
        
        # 直播设置
        live_group = QGroupBox("直播设置")
        live_layout = QGridLayout()
        live_layout.setSpacing(8)
        
        live_layout.addWidget(QLabel("录制时长限制："), 0, 0)
        self.live_record_limit_edit = QLineEdit("HH:mm:ss")
        self.live_record_limit_edit.setPlaceholderText("如: 01:00:00")
        self.live_record_limit_edit.setMinimumHeight(32)
        live_layout.addWidget(self.live_record_limit_edit, 0, 1)
        
        live_layout.addWidget(QLabel("刷新间隔(秒)："), 0, 2)
        self.live_wait_time_spin = QSpinBox()
        self.live_wait_time_spin.setRange(1, 3600)
        self.live_wait_time_spin.setValue(3)
        self.live_wait_time_spin.setMinimumHeight(32)
        self.live_wait_time_spin.setMaximumWidth(80)
        live_layout.addWidget(self.live_wait_time_spin, 0, 3)
        
        live_layout.addWidget(QLabel("首次分片数量："), 1, 0)
        live_take_count_layout = QHBoxLayout()
        self.live_take_count_enabled = QCheckBox()
        self.live_take_count_enabled.setChecked(True)
        live_take_count_layout.addWidget(self.live_take_count_enabled)
        
        self.live_take_count_spin = QSpinBox()
        self.live_take_count_spin.setRange(1, 100)
        self.live_take_count_spin.setValue(16)
        self.live_take_count_spin.setMinimumHeight(32)
        self.live_take_count_spin.setMaximumWidth(70)
        self.live_take_count_spin.setEnabled(True)
        live_take_count_layout.addWidget(self.live_take_count_spin)
        self.live_take_count_enabled.stateChanged.connect(self.toggle_live_take_count)
        live_layout.addLayout(live_take_count_layout, 1, 1)
        
        self.live_perform_as_vod = QCheckBox("按点播方式下载直播流")
        live_layout.addWidget(self.live_perform_as_vod, 1, 2)
        
        self.live_keep_segments = QCheckBox("实时合并时保留分片")
        self.live_keep_segments.setChecked(True)
        live_layout.addWidget(self.live_keep_segments, 1, 3)
        
        live_layout.addWidget(QLabel("任务开始时间："), 2, 0)
        self.task_start_at_edit = QLineEdit("yyyyMMddHHmmss")
        self.task_start_at_edit.setPlaceholderText("如: 20231225120000")
        self.task_start_at_edit.setMinimumHeight(32)
        live_layout.addWidget(self.task_start_at_edit, 2, 1, 1, 2)
        
        live_group.setLayout(live_layout)
        advanced_layout.addWidget(live_group)
        
        # 轨道选择设置
        track_group = QGroupBox("轨道选择设置")
        track_layout = QGridLayout()
        track_layout.setSpacing(8)
        
        track_layout.addWidget(QLabel("选择视频轨道："), 0, 0)
        self.select_video_edit = QLineEdit()
        self.select_video_edit.setPlaceholderText("正则表达式选择视频流")
        self.select_video_edit.setMinimumHeight(32)
        track_layout.addWidget(self.select_video_edit, 0, 1, 1, 2)
        
        track_layout.addWidget(QLabel("选择音频轨道："), 1, 0)
        self.select_audio_edit = QLineEdit()
        self.select_audio_edit.setPlaceholderText("正则表达式选择音频流")
        self.select_audio_edit.setMinimumHeight(32)
        track_layout.addWidget(self.select_audio_edit, 1, 1, 1, 2)
        
        track_layout.addWidget(QLabel("选择字幕轨道："), 2, 0)
        self.select_subtitle_edit = QLineEdit()
        self.select_subtitle_edit.setPlaceholderText("正则表达式选择字幕流")
        self.select_subtitle_edit.setMinimumHeight(32)
        track_layout.addWidget(self.select_subtitle_edit, 2, 1, 1, 2)
        
        track_layout.addWidget(QLabel("丢弃视频轨道："), 3, 0)
        self.drop_video_edit = QLineEdit()
        self.drop_video_edit.setPlaceholderText("正则表达式丢弃视频流")
        self.drop_video_edit.setMinimumHeight(32)
        track_layout.addWidget(self.drop_video_edit, 3, 1, 1, 2)
        
        track_layout.addWidget(QLabel("丢弃音频轨道："), 0, 3)
        self.drop_audio_edit = QLineEdit()
        self.drop_audio_edit.setPlaceholderText("正则表达式丢弃音频流")
        self.drop_audio_edit.setMinimumHeight(32)
        track_layout.addWidget(self.drop_audio_edit, 0, 4, 1, 2)
        
        track_layout.addWidget(QLabel("丢弃字幕轨道："), 1, 3)
        self.drop_subtitle_edit = QLineEdit()
        self.drop_subtitle_edit.setPlaceholderText("正则表达式丢弃字幕流")
        self.drop_subtitle_edit.setMinimumHeight(32)
        track_layout.addWidget(self.drop_subtitle_edit, 1, 4, 1, 2)
        
        track_layout.addWidget(QLabel("广告关键字："), 2, 3)
        self.ad_keyword_edit = QLineEdit()
        self.ad_keyword_edit.setPlaceholderText("设置广告分片的URL关键字")
        self.ad_keyword_edit.setMinimumHeight(32)
        track_layout.addWidget(self.ad_keyword_edit, 2, 4, 1, 2)
        
        track_layout.addWidget(QLabel("URL处理器参数："), 3, 3)
        self.urlprocessor_args_edit = QLineEdit()
        self.urlprocessor_args_edit.setPlaceholderText("直接传递给URL Processor")
        self.urlprocessor_args_edit.setMinimumHeight(32)
        track_layout.addWidget(self.urlprocessor_args_edit, 3, 4, 1, 2)
        
        track_group.setLayout(track_layout)
        advanced_layout.addWidget(track_group)
        
        # 解密/加密设置
        decrypt_group = QGroupBox("解密/加密设置")
        decrypt_layout = QGridLayout()
        decrypt_layout.setSpacing(8)
        
        decrypt_layout.addWidget(QLabel("解密引擎："), 0, 0)
        self.decryption_engine = QComboBox()
        self.decryption_engine.addItems(["MP4DECRYPT", "FFMPEG", "SHAKA_PACKAGER"])
        self.decryption_engine.setCurrentText("MP4DECRYPT")
        self.decryption_engine.setMinimumHeight(32)
        decrypt_layout.addWidget(self.decryption_engine, 0, 1)
        
        decrypt_layout.addWidget(QLabel("解密工具路径："), 0, 2)
        self.decryption_binary_path = QLineEdit()
        self.decryption_binary_path.setPlaceholderText("选择解密工具路径")
        self.decryption_binary_path.setMinimumHeight(32)
        decrypt_layout.addWidget(self.decryption_binary_path, 0, 3)
        
        decrypt_binary_btn = QPushButton("选择")
        decrypt_binary_btn.clicked.connect(self.browse_decryption_binary)
        decrypt_binary_btn.setMinimumWidth(70)
        decrypt_binary_btn.setMaximumWidth(70)
        decrypt_binary_btn.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                padding: 4px 6px;
                border-radius: 4px;
            }
        """)
        decrypt_layout.addWidget(decrypt_binary_btn, 0, 4)
        
        self.mp4_real_time_decryption = QCheckBox("MP4实时解密")
        decrypt_layout.addWidget(self.mp4_real_time_decryption, 1, 0)
        
        decrypt_layout.addWidget(QLabel("HLS加密方法："), 1, 1)
        self.custom_hls_method = QComboBox()
        self.custom_hls_method.addItems(["AES_128", "AES_128_ECB", "CENC", "CHACHA20", "NONE", "SAMPLE_AES", "SAMPLE_AES_CTR", "UNKNOWN"])
        self.custom_hls_method.setCurrentText("AES_128")
        self.custom_hls_method.setMinimumHeight(32)
        decrypt_layout.addWidget(self.custom_hls_method, 1, 2)
        
        decrypt_layout.addWidget(QLabel("HLS密钥："), 2, 0)
        self.custom_hls_key_edit = QLineEdit()
        self.custom_hls_key_edit.setPlaceholderText("文件、HEX或Base64")
        self.custom_hls_key_edit.setMinimumHeight(32)
        decrypt_layout.addWidget(self.custom_hls_key_edit, 2, 1, 1, 2)
        
        decrypt_layout.addWidget(QLabel("HLS IV："), 2, 3)
        self.custom_hls_iv_edit = QLineEdit()
        self.custom_hls_iv_edit.setPlaceholderText("文件、HEX或Base64")
        self.custom_hls_iv_edit.setMinimumHeight(32)
        decrypt_layout.addWidget(self.custom_hls_iv_edit, 2, 4)
        
        decrypt_group.setLayout(decrypt_layout)
        advanced_layout.addWidget(decrypt_group)
        
        # 字幕设置
        subtitle_group = QGroupBox("字幕设置")
        subtitle_layout = QGridLayout()
        subtitle_layout.setSpacing(8)
        
        subtitle_layout.addWidget(QLabel("仅下载字幕："), 0, 0)
        self.sub_only = QCheckBox()
        self.sub_only.setChecked(False)
        subtitle_layout.addWidget(self.sub_only, 0, 1)
        
        subtitle_layout.addWidget(QLabel("字幕格式："), 0, 2)
        self.sub_format = QComboBox()
        self.sub_format.addItems(["SRT", "VTT"])
        self.sub_format.setCurrentText("SRT")
        self.sub_format.setMinimumHeight(32)
        subtitle_layout.addWidget(self.sub_format, 0, 3)
        
        subtitle_layout.addWidget(QLabel("自动修复字幕："), 0, 4)
        self.auto_subtitle_fix = QCheckBox()
        self.auto_subtitle_fix.setChecked(True)
        subtitle_layout.addWidget(self.auto_subtitle_fix, 0, 5)
        
        subtitle_layout.addWidget(QLabel("音频修正VTT："), 1, 0)
        self.live_fix_vtt_by_audio = QCheckBox()
        self.live_fix_vtt_by_audio.setChecked(False)
        subtitle_layout.addWidget(self.live_fix_vtt_by_audio, 1, 1)
        
        subtitle_group.setLayout(subtitle_layout)
        advanced_layout.addWidget(subtitle_group)
        
        # 代理设置
        proxy_group = QGroupBox("代理设置")
        proxy_layout = QGridLayout()
        proxy_layout.setSpacing(8)
        
        proxy_layout.addWidget(QLabel("自定义代理："), 0, 0)
        self.custom_proxy = QLineEdit()
        self.custom_proxy.setPlaceholderText("如 http://127.0.0.1:8888")
        self.custom_proxy.setMinimumHeight(32)
        proxy_layout.addWidget(self.custom_proxy, 0, 1, 1, 2)
        
        proxy_layout.addWidget(QLabel("不使用系统代理："), 1, 0)
        self.no_system_proxy = QCheckBox()
        self.no_system_proxy.setChecked(True)
        proxy_layout.addWidget(self.no_system_proxy, 1, 1)
        
        proxy_group.setLayout(proxy_layout)
        advanced_layout.addWidget(proxy_group)
        
        # 高级选项
        advanced_options_group = QGroupBox("高级选项")
        advanced_options_layout = QGridLayout()
        advanced_options_layout.setSpacing(8)
        
        # 第一行
        advanced_options_layout.addWidget(QLabel("日志级别："), 0, 0)
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARN", "ERROR", "OFF"])
        self.log_level.setCurrentText("INFO")
        self.log_level.setMinimumHeight(32)
        advanced_options_layout.addWidget(self.log_level, 0, 1)
        
        advanced_options_layout.addWidget(QLabel("UI语言："), 0, 2)
        self.ui_language = QComboBox()
        self.ui_language.addItems(["en-US", "zh-CN", "zh-TW"])
        self.ui_language.setCurrentText("zh-CN")
        self.ui_language.setMinimumHeight(32)
        advanced_options_layout.addWidget(self.ui_language, 0, 3)
        
        # 第二行
        advanced_options_layout.addWidget(QLabel("强制ANSI控制台："), 1, 0)
        self.force_ansi_console = QCheckBox()
        advanced_options_layout.addWidget(self.force_ansi_console, 1, 1)
        
        advanced_options_layout.addWidget(QLabel("去除ANSI颜色："), 1, 2)
        self.no_ansi_color = QCheckBox()
        advanced_options_layout.addWidget(self.no_ansi_color, 1, 3)
        
        # 第三行
        advanced_options_layout.addWidget(QLabel("使用ffmpeg concat分离器："), 2, 0)
        self.use_ffmpeg_concat_demuxer = QCheckBox()
        advanced_options_layout.addWidget(self.use_ffmpeg_concat_demuxer, 2, 1)
        
        advanced_options_layout.addWidget(QLabel("写入元数据json："), 2, 2)
        self.write_meta_json = QCheckBox()
        self.write_meta_json.setChecked(True)
        advanced_options_layout.addWidget(self.write_meta_json, 2, 3)
        
        # 第四行
        advanced_options_layout.addWidget(QLabel("追加URL参数："), 3, 0)
        self.append_url_params = QCheckBox()
        advanced_options_layout.addWidget(self.append_url_params, 3, 1)
        
        advanced_options_layout.addWidget(QLabel("允许HLS多EXT-MAP："), 3, 2)
        self.allow_hls_multi_ext_map = QCheckBox()
        advanced_options_layout.addWidget(self.allow_hls_multi_ext_map, 3, 3)
        
        # 第五行
        advanced_options_layout.addWidget(QLabel("下载完成后不合并："), 4, 0)
        self.no_merge = QCheckBox()
        advanced_options_layout.addWidget(self.no_merge, 4, 1)
        
        advanced_options_layout.addWidget(QLabel("合并时不写入日期："), 4, 2)
        self.no_date_in_name = QCheckBox()
        self.no_date_in_name.setChecked(True)
        advanced_options_layout.addWidget(self.no_date_in_name, 4, 3)
        
        # 第六行
        advanced_options_layout.addWidget(QLabel("关闭日志文件输出："), 5, 0)
        self.no_log = QCheckBox()
        advanced_options_layout.addWidget(self.no_log, 5, 1)
        
        advanced_options_layout.addWidget(QLabel("禁用更新检查："), 5, 2)
        self.disable_update_check = QCheckBox()
        self.disable_update_check.setChecked(False)
        advanced_options_layout.addWidget(self.disable_update_check, 5, 3)
        
        advanced_options_group.setLayout(advanced_options_layout)
        advanced_layout.addWidget(advanced_options_group)
        
        advanced_layout.addStretch()
        
        # 将高级标签页添加到标签页容器
        self.tab_widget.addTab(advanced_scroll, "高级设置")
        
        main_layout.addWidget(self.tab_widget, 1)
        
        # 进度条和命令显示区域
        bottom_controls_layout = QVBoxLayout()
        
        # 进度条
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("下载进度："))
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #cccccc;
                border-radius: 5px;
                text-align: center;
                background-color: #f0f0f0;
                font-size: 10pt;
            }
            QProgressBar::chunk {
                background-color: #ffb8c6;
                border-radius: 4px;
            }
        """)
        progress_layout.addWidget(self.progress_bar, 1)
        bottom_controls_layout.addLayout(progress_layout)
        
        # 命令显示和操作按钮
        command_layout = QVBoxLayout()
        
        # 命令显示
        self.command_edit = QLineEdit()
        self.command_edit.setReadOnly(True)
        self.command_edit.setMinimumHeight(32)
        self.command_edit.setStyleSheet("""
            QLineEdit {
                background-color: #f5f5f5;
                border: 1px solid #cccccc;
                padding: 6px 10px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 10pt;
                border-radius: 5px;
                color: #333333;
            }
        """)
        command_layout.addWidget(self.command_edit)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.go_btn = QPushButton("🚀 开始下载 (GO)")
        self.go_btn.clicked.connect(self.start_download)
        self.go_btn.setMinimumHeight(38)
        self.go_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12pt;
                border: 1px solid #555555;
            }
            QPushButton:hover {
                background-color: #444444;
                border: 1px solid #666666;
            }
            QPushButton:pressed {
                background-color: #ffb8c6;
                color: #333333;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
                border: 1px solid #aaaaaa;
            }
        """)
        button_layout.addWidget(self.go_btn)
        
        self.stop_btn = QPushButton("⏹️ 停止下载")
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12pt;
                border: none;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        button_layout.addWidget(self.stop_btn)
        
        # 添加"生成命令"按钮
        generate_cmd_btn = QPushButton("🔧 生成命令")
        generate_cmd_btn.clicked.connect(self.generate_command)
        generate_cmd_btn.setMinimumHeight(38)
        generate_cmd_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12pt;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        button_layout.addWidget(generate_cmd_btn)
        
        button_layout.addStretch()
        command_layout.addLayout(button_layout)
        bottom_controls_layout.addLayout(command_layout)
        
        main_layout.addLayout(bottom_controls_layout)
        
        # 日志区域
        log_group = QGroupBox("📝 运行日志")
        log_layout = QVBoxLayout()
        
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(120)
        self.log_edit.setMaximumHeight(180)
        self.log_edit.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
                border: 1px solid #cccccc;
                border-radius: 5px;
                color: #333333;
            }
        """)
        log_layout.addWidget(self.log_edit)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # 底部链接
        link_layout = QHBoxLayout()
        link_label = QLabel()
        link_label.setOpenExternalLinks(True)
        link_label.setText('<a href="https://github.com/arisa20180524/N_m3u8DL-RE-GUI-Miix/tree/main" style="color: #0066cc; text-decoration: none; font-size: 10pt;">🔗 Miix&教程</a>')
        link_layout.addWidget(link_label)
        
        link_layout.addStretch()
        main_layout.addLayout(link_layout)
        
        # 设置全局样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: white;
                font-size: 10pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel {
                color: #333333;
                font-size: 10pt;
            }
            QLineEdit, QSpinBox, QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px 8px;
                background-color: white;
                selection-background-color: #ffb8c6;
                font-size: 10pt;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 2px solid #999999;
            }
            QCheckBox {
                spacing: 5px;
                color: #333333;
                font-size: 10pt;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #ffb8c6;
                border: 1px solid #ffa0b2;
                border-radius: 3px;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                border-radius: 5px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                color: #666666;
                font-size: 10pt;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #ffb8c6;
                color: #333333;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #e8e8e8;
            }
            QPushButton {
                font-weight: bold;
                border-radius: 5px;
                padding: 6px 12px;
                font-size: 10pt;
            }
            QScrollArea {
                border: none;
                background-color: white;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #cccccc;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #aaaaaa;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        
        # 设置字体
        self.setFont(QFont("Microsoft YaHei", 9))
    
    def clear_log(self):
        """清空日志"""
        self.log_edit.clear()
        self.update_log.emit("日志已清空")
    
    def generate_command(self):
        """生成命令但不执行"""
        try:
            cmd = self.build_command()
            self.command_edit.setText(' '.join(cmd))
            self.update_log.emit("命令已生成，可以复制使用")
        except Exception as e:
            self.update_log.emit(f"生成命令时出错：{str(e)}")
    
    def build_command(self):
        """构建命令行参数"""
        cmd = [self.executable_edit.text()]
        cmd.append(self.m3u8_url_edit.text())
        
        if self.title_edit.text():
            cmd.extend(["--save-name", self.title_edit.text()])
        
        if self.work_dir_edit.text():
            cmd.extend(["--save-dir", self.work_dir_edit.text()])
        
        if self.tmp_dir_edit.text():
            cmd.extend(["--tmp-dir", self.tmp_dir_edit.text()])
        
        if self.save_pattern_edit.text():
            cmd.extend(["--save-pattern", self.save_pattern_edit.text()])
        
        if self.log_file_path_edit.text():
            cmd.extend(["--log-file-path", self.log_file_path_edit.text()])
        
        if self.ffmpeg_path_edit.text():
            cmd.extend(["--ffmpeg-binary-path", self.ffmpeg_path_edit.text()])
        
        if self.headers_edit.text():
            headers = self.headers_edit.text().strip()
            if headers:
                for header in headers.split(';'):
                    header = header.strip()
                    if header:
                        cmd.extend(["-H", header])
        
        if self.baseurl_edit.text():
            cmd.extend(["--base-url", self.baseurl_edit.text()])
        
        if self.mux_file_edit.text():
            cmd.extend(["--mux-import", self.mux_file_edit.text()])
        
        if self.start_time_edit.text() != "00:00:00" or self.end_time_edit.text() != "00:00:00":
            range_str = f"{self.start_time_edit.text()}-{self.end_time_edit.text()}"
            cmd.extend(["--custom-range", range_str])
        
        # 基础选项
        if self.del_after_merge.isChecked():
            cmd.append("--del-after-done")
        
        if self.no_date_in_name.isChecked():
            cmd.append("--no-date-info")
        
        if self.no_system_proxy.isChecked():
            cmd.append("--use-system-proxy=false")
        
        if self.only_parse_m3u8.isChecked():
            cmd.append("--skip-download")
        
        if self.mux_while_download.isChecked():
            cmd.extend(["--live-real-time-merge", "--live-pipe-mux"])
        
        if self.no_merge.isChecked():
            cmd.append("--skip-merge")
        
        if self.binary_merge.isChecked():
            cmd.append("--binary-merge")
        
        if self.auto_select.isChecked():
            cmd.append("--auto-select")
        
        if self.no_log.isChecked():
            cmd.append("--no-log")
        
        if self.check_segments_count.isChecked():
            cmd.append("--check-segments-count")
        
        if self.concurrent_download.isChecked():
            cmd.append("--concurrent-download")
        
        if self.merge_to_mp4.isChecked():
            cmd.extend(["-M", "format=mp4"])
        
        # 性能设置
        cmd.extend(["--thread-count", str(self.max_threads.value())])
        cmd.extend(["--download-retry-count", str(self.retry_count.value())])
        cmd.extend(["--http-request-timeout", str(self.timeout.value())])
        
        if self.limit_speed.value() > 0:
            cmd.extend(["--max-speed", f"{self.limit_speed.value()}K"])
        
        # 字幕设置
        if self.sub_only.isChecked():
            cmd.append("--sub-only")
        
        cmd.extend(["--sub-format", self.sub_format.currentText()])
        
        if not self.auto_subtitle_fix.isChecked():
            cmd.append("--auto-subtitle-fix=false")
        
        if self.live_fix_vtt_by_audio.isChecked():
            cmd.append("--live-fix-vtt-by-audio")
        
        # 代理设置
        if self.custom_proxy.text():
            cmd.extend(["--custom-proxy", self.custom_proxy.text()])
        
        # 高级设置
        cmd.extend(["--log-level", self.log_level.currentText()])
        cmd.extend(["--ui-language", self.ui_language.currentText()])
        
        if self.force_ansi_console.isChecked():
            cmd.append("--force-ansi-console")
        
        if self.no_ansi_color.isChecked():
            cmd.append("--no-ansi-color")
        
        if self.use_ffmpeg_concat_demuxer.isChecked():
            cmd.append("--use-ffmpeg-concat-demuxer")
        
        if not self.write_meta_json.isChecked():
            cmd.append("--write-meta-json=false")
        
        if self.append_url_params.isChecked():
            cmd.append("--append-url-params")
        
        if self.allow_hls_multi_ext_map.isChecked():
            cmd.append("--allow-hls-multi-ext-map")
        
        if self.disable_update_check.isChecked():
            cmd.append("--disable-update-check")
        
        # 解密/加密设置
        if self.key_edit.text():
            cmd.extend(["--key", self.key_edit.text()])
        
        if self.key_text_file_edit.text():
            cmd.extend(["--key-text-file", self.key_text_file_edit.text()])
        
        cmd.extend(["--decryption-engine", self.decryption_engine.currentText()])
        
        if self.decryption_binary_path.text():
            cmd.extend(["--decryption-binary-path", self.decryption_binary_path.text()])
        
        if self.mp4_real_time_decryption.isChecked():
            cmd.append("--mp4-real-time-decryption")
        
        if self.custom_hls_method.currentText() != "AES_128":
            cmd.extend(["--custom-hls-method", self.custom_hls_method.currentText()])
        
        if self.custom_hls_key_edit.text():
            cmd.extend(["--custom-hls-key", self.custom_hls_key_edit.text()])
        
        if self.custom_hls_iv_edit.text():
            cmd.extend(["--custom-hls-iv", self.custom_hls_iv_edit.text()])
        
        # 直播设置
        if self.live_record_limit_edit.text() != "HH:mm:ss":
            cmd.extend(["--live-record-limit", self.live_record_limit_edit.text()])
        
        if self.live_wait_time_spin.value() != 3:
            cmd.extend(["--live-wait-time", str(self.live_wait_time_spin.value())])
        
        if self.live_take_count_enabled.isChecked() and self.live_take_count_spin.value() != 16:
            cmd.extend(["--live-take-count", str(self.live_take_count_spin.value())])
        
        if self.live_perform_as_vod.isChecked():
            cmd.append("--live-perform-as-vod")
        
        if not self.live_keep_segments.isChecked():
            cmd.append("--live-keep-segments=false")
        
        if self.task_start_at_edit.text() != "yyyyMMddHHmmss":
            cmd.extend(["--task-start-at", self.task_start_at_edit.text()])
        
        # 轨道选择设置
        if self.select_video_edit.text():
            cmd.extend(["--select-video", self.select_video_edit.text()])
        
        if self.select_audio_edit.text():
            cmd.extend(["--select-audio", self.select_audio_edit.text()])
        
        if self.select_subtitle_edit.text():
            cmd.extend(["--select-subtitle", self.select_subtitle_edit.text()])
        
        if self.drop_video_edit.text():
            cmd.extend(["--drop-video", self.drop_video_edit.text()])
        
        if self.drop_audio_edit.text():
            cmd.extend(["--drop-audio", self.drop_audio_edit.text()])
        
        if self.drop_subtitle_edit.text():
            cmd.extend(["--drop-subtitle", self.drop_subtitle_edit.text()])
        
        if self.ad_keyword_edit.text():
            cmd.extend(["--ad-keyword", self.ad_keyword_edit.text()])
        
        if self.urlprocessor_args_edit.text():
            cmd.extend(["--urlprocessor-args", self.urlprocessor_args_edit.text()])
        
        # 自定义参数
        if self.args_edit.text():
            custom_args = self.args_edit.text().split()
            cmd.extend(custom_args)
        
        return cmd
    
    def toggle_live_take_count(self, state):
        """切换首次分片数量启用状态"""
        self.live_take_count_spin.setEnabled(state == Qt.Checked)
    
    def browse_directory(self, line_edit):
        """通用目录选择函数"""
        dirname = QFileDialog.getExistingDirectory(
            self, "选择目录", 
            line_edit.text() or os.getcwd()
        )
        if dirname:
            line_edit.setText(dirname)
    
    def browse_file(self, line_edit, filter_text):
        """通用文件选择函数"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择文件", 
            os.path.dirname(line_edit.text()) or os.getcwd(), 
            filter_text
        )
        if filename:
            line_edit.setText(filename)
    
    def toggle_pin_window(self):
        """切换窗口置顶状态"""
        self.is_always_on_top = not self.is_always_on_top
        
        if self.is_always_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.pin_btn.setChecked(True)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.pin_btn.setChecked(False)
        
        self.show()
    
    def browse_executable(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择执行程序", 
            os.path.dirname(self.executable_edit.text()) or os.getcwd(), 
            "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if filename:
            self.executable_edit.setText(filename)
    
    def browse_work_dir(self):
        dirname = QFileDialog.getExistingDirectory(
            self, "选择工作目录", 
            self.work_dir_edit.text() or os.getcwd()
        )
        if dirname:
            self.work_dir_edit.setText(dirname)
    
    def browse_ffmpeg_path(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择FFmpeg可执行文件", 
            os.path.dirname(self.ffmpeg_path_edit.text()) or os.getcwd(), 
            "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if filename:
            self.ffmpeg_path_edit.setText(filename)
    
    def browse_mux_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择混流文件", 
            os.path.dirname(self.mux_file_edit.text()) or os.getcwd(), 
            "所有文件 (*.*)"
        )
        if filename:
            self.mux_file_edit.setText(filename)
    
    def browse_decryption_binary(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择解密工具", 
            os.path.dirname(self.decryption_binary_path.text()) or os.getcwd(), 
            "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if filename:
            self.decryption_binary_path.setText(filename)
    
    def save_settings(self):
        """保存所有设置到JSON文件"""
        settings = self.get_current_settings()
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存设置", 
            os.path.join(os.getcwd(), "m3u8_downloader_settings.json"), 
            "JSON文件 (*.json);;所有文件 (*.*)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=4)
                # 同时保存到默认位置
                default_path = os.path.join(os.path.expanduser("~"), "m3u8_downloader_last_settings.json")
                with open(default_path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=4)
                self.update_log.emit(f"设置已保存到：{filename}")
                QMessageBox.information(self, "保存成功", "所有设置已成功保存到JSON文件！")
            except Exception as e:
                self.update_log.emit(f"保存设置时出错：{str(e)}")
                QMessageBox.critical(self, "保存失败", f"保存设置时出错：{str(e)}")
    
    def get_current_settings(self):
        """获取当前所有设置"""
        return {
            "executable": self.executable_edit.text(),
            "work_dir": self.work_dir_edit.text(),
            "ffmpeg_path": self.ffmpeg_path_edit.text(),
            "m3u8_url": self.m3u8_url_edit.text(),
            "title": self.title_edit.text(),
            "headers": self.headers_edit.text(),
            "baseurl": self.baseurl_edit.text(),
            "mux_file": self.mux_file_edit.text(),
            "start_time": self.start_time_edit.text(),
            "end_time": self.end_time_edit.text(),
            "max_threads": self.max_threads.value(),
            "retry_count": self.retry_count.value(),
            "timeout": self.timeout.value(),
            "limit_speed": self.limit_speed.value(),
            "del_after_merge": self.del_after_merge.isChecked(),
            "only_parse_m3u8": self.only_parse_m3u8.isChecked(),
            "mux_while_download": self.mux_while_download.isChecked(),
            "binary_merge": self.binary_merge.isChecked(),
            "auto_select": self.auto_select.isChecked(),
            "check_segments_count": self.check_segments_count.isChecked(),
            "concurrent_download": self.concurrent_download.isChecked(),
            "merge_to_mp4": self.merge_to_mp4.isChecked(),
            "args": self.args_edit.text(),
            "key": self.key_edit.text(),
            "tmp_dir": self.tmp_dir_edit.text(),
            "save_pattern": self.save_pattern_edit.text(),
            "log_file_path": self.log_file_path_edit.text(),
            "key_text_file": self.key_text_file_edit.text(),
            "live_record_limit": self.live_record_limit_edit.text(),
            "live_wait_time": self.live_wait_time_spin.value(),
            "live_take_count_enabled": self.live_take_count_enabled.isChecked(),
            "live_take_count": self.live_take_count_spin.value(),
            "live_perform_as_vod": self.live_perform_as_vod.isChecked(),
            "live_keep_segments": self.live_keep_segments.isChecked(),
            "task_start_at": self.task_start_at_edit.text(),
            "select_video": self.select_video_edit.text(),
            "select_audio": self.select_audio_edit.text(),
            "select_subtitle": self.select_subtitle_edit.text(),
            "drop_video": self.drop_video_edit.text(),
            "drop_audio": self.drop_audio_edit.text(),
            "drop_subtitle": self.drop_subtitle_edit.text(),
            "ad_keyword": self.ad_keyword_edit.text(),
            "urlprocessor_args": self.urlprocessor_args_edit.text(),
            "decryption_engine": self.decryption_engine.currentText(),
            "decryption_binary_path": self.decryption_binary_path.text(),
            "mp4_real_time_decryption": self.mp4_real_time_decryption.isChecked(),
            "custom_hls_method": self.custom_hls_method.currentText(),
            "custom_hls_key": self.custom_hls_key_edit.text(),
            "custom_hls_iv": self.custom_hls_iv_edit.text(),
            "sub_only": self.sub_only.isChecked(),
            "sub_format": self.sub_format.currentText(),
            "auto_subtitle_fix": self.auto_subtitle_fix.isChecked(),
            "live_fix_vtt_by_audio": self.live_fix_vtt_by_audio.isChecked(),
            "custom_proxy": self.custom_proxy.text(),
            "no_system_proxy": self.no_system_proxy.isChecked(),
            "log_level": self.log_level.currentText(),
            "ui_language": self.ui_language.currentText(),
            "force_ansi_console": self.force_ansi_console.isChecked(),
            "no_ansi_color": self.no_ansi_color.isChecked(),
            "use_ffmpeg_concat_demuxer": self.use_ffmpeg_concat_demuxer.isChecked(),
            "write_meta_json": self.write_meta_json.isChecked(),
            "append_url_params": self.append_url_params.isChecked(),
            "allow_hls_multi_ext_map": self.allow_hls_multi_ext_map.isChecked(),
            "no_merge": self.no_merge.isChecked(),
            "no_date_in_name": self.no_date_in_name.isChecked(),
            "no_log": self.no_log.isChecked(),
            "disable_update_check": self.disable_update_check.isChecked(),
            "always_on_top": self.is_always_on_top
        }
    
    def load_settings(self):
        """从JSON文件加载设置"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "加载设置", 
            os.getcwd(), 
            "JSON文件 (*.json);;所有文件 (*.*)"
        )
        
        if filename:
            self.load_settings_from_file(filename)
    
    def load_settings_from_file(self, filename):
        """从指定文件加载设置"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            self.apply_settings(settings)
            self.update_log.emit(f"设置已从 {filename} 加载")
            QMessageBox.information(self, "加载成功", "设置已成功从JSON文件加载！")
        except Exception as e:
            self.update_log.emit(f"加载设置时出错：{str(e)}")
            QMessageBox.critical(self, "加载失败", f"加载设置时出错：{str(e)}")
    
    def apply_settings(self, settings):
        """应用设置到界面"""
        # 路径设置
        self.executable_edit.setText(settings.get("executable", ""))
        self.work_dir_edit.setText(settings.get("work_dir", ""))
        self.ffmpeg_path_edit.setText(settings.get("ffmpeg_path", ""))
        
        # 下载设置
        self.m3u8_url_edit.setText(settings.get("m3u8_url", ""))
        self.title_edit.setText(settings.get("title", ""))
        self.headers_edit.setText(settings.get("headers", ""))
        self.baseurl_edit.setText(settings.get("baseurl", ""))
        self.mux_file_edit.setText(settings.get("mux_file", ""))
        
        # 范围选择
        self.start_time_edit.setText(settings.get("start_time", "00:00:00"))
        self.end_time_edit.setText(settings.get("end_time", "00:00:00"))
        
        # 性能设置
        self.max_threads.setValue(settings.get("max_threads", 32))
        self.retry_count.setValue(settings.get("retry_count", 15))
        self.timeout.setValue(settings.get("timeout", 100))
        self.limit_speed.setValue(settings.get("limit_speed", 0))
        
        # 基础选项
        self.del_after_merge.setChecked(settings.get("del_after_merge", True))
        self.only_parse_m3u8.setChecked(settings.get("only_parse_m3u8", False))
        self.mux_while_download.setChecked(settings.get("mux_while_download", False))
        self.binary_merge.setChecked(settings.get("binary_merge", False))
        self.auto_select.setChecked(settings.get("auto_select", True))
        self.check_segments_count.setChecked(settings.get("check_segments_count", True))
        self.concurrent_download.setChecked(settings.get("concurrent_download", True))
        self.merge_to_mp4.setChecked(settings.get("merge_to_mp4", True))
        
        # 高级参数
        self.args_edit.setText(settings.get("args", ""))
        self.key_edit.setText(settings.get("key", ""))
        
        # 输出设置
        self.tmp_dir_edit.setText(settings.get("tmp_dir", ""))
        self.save_pattern_edit.setText(settings.get("save_pattern", ""))
        self.log_file_path_edit.setText(settings.get("log_file_path", ""))
        self.key_text_file_edit.setText(settings.get("key_text_file", ""))
        
        # 直播设置
        self.live_record_limit_edit.setText(settings.get("live_record_limit", "HH:mm:ss"))
        self.live_wait_time_spin.setValue(settings.get("live_wait_time", 3))
        self.live_take_count_enabled.setChecked(settings.get("live_take_count_enabled", True))
        self.live_take_count_spin.setValue(settings.get("live_take_count", 16))
        self.live_perform_as_vod.setChecked(settings.get("live_perform_as_vod", False))
        self.live_keep_segments.setChecked(settings.get("live_keep_segments", True))
        self.task_start_at_edit.setText(settings.get("task_start_at", "yyyyMMddHHmmss"))
        
        # 轨道选择设置
        self.select_video_edit.setText(settings.get("select_video", ""))
        self.select_audio_edit.setText(settings.get("select_audio", ""))
        self.select_subtitle_edit.setText(settings.get("select_subtitle", ""))
        self.drop_video_edit.setText(settings.get("drop_video", ""))
        self.drop_audio_edit.setText(settings.get("drop_audio", ""))
        self.drop_subtitle_edit.setText(settings.get("drop_subtitle", ""))
        self.ad_keyword_edit.setText(settings.get("ad_keyword", ""))
        self.urlprocessor_args_edit.setText(settings.get("urlprocessor_args", ""))
        
        # 解密/加密设置
        self.decryption_engine.setCurrentText(settings.get("decryption_engine", "MP4DECRYPT"))
        self.decryption_binary_path.setText(settings.get("decryption_binary_path", ""))
        self.mp4_real_time_decryption.setChecked(settings.get("mp4_real_time_decryption", False))
        self.custom_hls_method.setCurrentText(settings.get("custom_hls_method", "AES_128"))
        self.custom_hls_key_edit.setText(settings.get("custom_hls_key", ""))
        self.custom_hls_iv_edit.setText(settings.get("custom_hls_iv", ""))
        
        # 字幕设置
        self.sub_only.setChecked(settings.get("sub_only", False))
        self.sub_format.setCurrentText(settings.get("sub_format", "SRT"))
        self.auto_subtitle_fix.setChecked(settings.get("auto_subtitle_fix", True))
        self.live_fix_vtt_by_audio.setChecked(settings.get("live_fix_vtt_by_audio", False))
        
        # 代理设置
        self.custom_proxy.setText(settings.get("custom_proxy", ""))
        self.no_system_proxy.setChecked(settings.get("no_system_proxy", True))
        
        # 高级选项
        self.log_level.setCurrentText(settings.get("log_level", "INFO"))
        self.ui_language.setCurrentText(settings.get("ui_language", "zh-CN"))
        self.force_ansi_console.setChecked(settings.get("force_ansi_console", False))
        self.no_ansi_color.setChecked(settings.get("no_ansi_color", False))
        self.use_ffmpeg_concat_demuxer.setChecked(settings.get("use_ffmpeg_concat_demuxer", False))
        self.write_meta_json.setChecked(settings.get("write_meta_json", True))
        self.append_url_params.setChecked(settings.get("append_url_params", False))
        self.allow_hls_multi_ext_map.setChecked(settings.get("allow_hls_multi_ext_map", False))
        self.no_merge.setChecked(settings.get("no_merge", False))
        self.no_date_in_name.setChecked(settings.get("no_date_in_name", True))
        self.no_log.setChecked(settings.get("no_log", False))
        self.disable_update_check.setChecked(settings.get("disable_update_check", False))
        
        # 窗口设置
        is_always_on_top = settings.get("always_on_top", False)
        if is_always_on_top:
            self.toggle_pin_window()
        
        self.toggle_live_take_count(Qt.Checked if self.live_take_count_enabled.isChecked() else Qt.Unchecked)
    
    def load_last_settings(self):
        """加载上次的设置"""
        try:
            default_path = os.path.join(os.path.expanduser("~"), "m3u8_downloader_last_settings.json")
            if os.path.exists(default_path):
                with open(default_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                self.apply_settings(settings)
                self.update_log.emit("已加载上次的设置")
        except Exception as e:
            pass  # 静默失败
    
    def start_download(self):
        """开始下载"""
        # 检查必要参数
        if not os.path.exists(self.executable_edit.text()):
            QMessageBox.critical(self, "错误", "执行程序不存在！")
            return
        
        if not self.m3u8_url_edit.text():
            QMessageBox.critical(self, "错误", "请输入M3U8地址！")
            return
        
        # 禁用GO按钮，启用停止按钮
        self.go_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # 清空日志和进度条
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        
        # 构建命令
        try:
            cmd = self.build_command()
            work_dir = self.work_dir_edit.text() if self.work_dir_edit.text() else os.path.dirname(self.executable_edit.text())
            
            # 创建下载线程
            self.download_thread = DownloadThread(cmd, work_dir)
            self.download_thread.update_progress.connect(self.on_update_progress)
            self.download_thread.update_log.connect(self.on_update_log)
            self.download_thread.download_complete.connect(self.on_download_complete)
            self.download_thread.command_ready.connect(self.command_edit.setText)
            
            self.download_thread.start()
            
        except Exception as e:
            self.update_log.emit(f"启动下载时出错：{str(e)}")
            self.go_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
    
    def stop_download(self):
        """停止下载"""
        if self.download_thread:
            self.update_log.emit("正在停止下载...")
            self.download_thread.stop()
    
    def on_update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def on_update_log(self, text):
        self.log_edit.append(text)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
    
    def on_download_complete(self, exit_code):
        if exit_code == 0:
            self.update_log.emit("✅ 下载完成！")
        elif exit_code == -1:
            self.update_log.emit("⏹️ 下载已停止")
        else:
            self.update_log.emit(f"❌ 下载失败，退出代码：{exit_code}")
        
        # 恢复按钮状态
        self.go_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        # 重置进度条（保持最终进度）
        if exit_code != 0:
            self.progress_bar.setValue(0)
        
        # 保存当前设置
        try:
            settings = self.get_current_settings()
            default_path = os.path.join(os.path.expanduser("~"), "m3u8_downloader_last_settings.json")
            with open(default_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except:
            pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 设置全局字体
    font = QFont()
    font.setFamily("Microsoft YaHei")
    app.setFont(font)
    
    # 创建并显示主窗口
    window = M3U8Downloader()
    window.show()
    
    sys.exit(app.exec_())
    
