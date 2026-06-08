import network  # 网络模块，用于处理 WiFi 连接 / Network module for handling WiFi connections
import os      # 操作系统接口模块 / Operating system interface module
import time    # 时间模块，用于延时操作 / Time module for delay operations
import _thread # 线程模块，用于多线程操作 / Thread module for multithreading operations
import gc      # 垃圾回收模块，用于内存管理 / Garbage collection module for memory management
import sys     # 系统模块，用于系统相关操作 / System module for system-related operations
import random  # 随机数模块 / Random number module
import ujson   # JSON 处理模块 / JSON processing module
import utime   # 微秒级时间模块 / Microsecond-level time module
import ulab.numpy as np  # 数值计算库 / Numerical computation library
import nncase_runtime as nn  # 神经网络运行时库 / Neural network runtime library
import aidemo  # AI 演示模块 / AI demo module
import image   # 图像处理模块 / Image processing module
import multimedia as mm  # 多媒体模块 / Multimedia module
from time import sleep  # 从 time 模块导入 sleep 函数 / Import sleep function from time module
from media.vencoder import *  # 从媒体模块导入视频编码器相关功能 / Import video encoder-related functions from media module
from media.sensor import *    # 从媒体模块导入传感器相关功能 / Import sensor-related functions from media module
from media.media import *     # 从媒体模块导入媒体管理功能 / Import media management functions from media module
from media.display import *   # 从媒体模块导入显示相关功能 / Import display-related functions from media module
from libs.PipeLine import PipeLine, ScopedTiming  # 从 libs 导入 PipeLine 和 ScopedTiming 类 / Import PipeLine and ScopedTiming classes from libs
from libs.AIBase import AIBase  # 从 libs 导入 AIBase 类 / Import AIBase class from libs
from libs.AI2D import Ai2d      # 从 libs 导入 Ai2d 类 / Import Ai2d class from libs

class PTZTimer:
   # """PTZ patrol timer. Call update() repeatedly in the main loop."""

    PERIOD_MS = 0.1 * 60 * 1000
    SERVO_PERIOD_MS = 20
    MIN_PULSE_MS = 0.5
    MAX_PULSE_MS = 2.5

    def __init__(
        self,
        pan_pwm_id=0,
        tilt_pwm_id=1,
        pan_pin=42,
        tilt_pin=43,
        pan_center_ms=1.47,
        tilt_center_ms=1.60,
        period_ms=PERIOD_MS,
    ):
        from machine import FPIOA, PWM

        self.period_ms = period_ms
        self.pan_center_ms = pan_center_ms
        self.tilt_center_ms = tilt_center_ms
        self.index = 0
        self.last_move_ms = time.ticks_ms()

        # Same wiring as finall.py: GPIO42/PWM0 is pan, GPIO43/PWM1 is tilt.
        fpioa = FPIOA()
        fpioa.set_function(pan_pin, FPIOA.PWM0)
        fpioa.set_function(tilt_pin, FPIOA.PWM1)

        self.pan = PWM(pan_pwm_id, 50)
        self.tilt = PWM(tilt_pwm_id, 50)
        self.pan.enable(1)
        self.tilt.enable(1)

        # Each tuple is (pan_ms, tilt_ms). Tilt stays centered by default.
        self.presets = (
            (self.pan_center_ms, self.tilt_center_ms),
            (1.20, self.tilt_center_ms),
            (self.pan_center_ms, self.tilt_center_ms),
            (1.80, self.tilt_center_ms),
            (self.pan_center_ms, self.tilt_center_ms),
        )

        self.move_to(self.pan_center_ms, self.tilt_center_ms)

    def _clamp(self, value, min_value, max_value):
        if value < min_value:
            return min_value
        if value > max_value:
            return max_value
        return value

    def _pulse_to_duty(self, pulse_ms):
        pulse_ms = self._clamp(pulse_ms, self.MIN_PULSE_MS, self.MAX_PULSE_MS)
        return round(pulse_ms / self.SERVO_PERIOD_MS * 100, 2)

    def move_to(self, pan_ms, tilt_ms):
        self.pan.duty(self._pulse_to_duty(pan_ms))
        self.tilt.duty(self._pulse_to_duty(tilt_ms))

    def move_next(self):
        self.index = (self.index + 1) % len(self.presets)
        pan_ms, tilt_ms = self.presets[self.index]
        self.move_to(pan_ms, tilt_ms)
        return self.index, pan_ms, tilt_ms

    def update(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_move_ms) >= self.period_ms:
            self.last_move_ms = now
            return self.move_next()
        return None

    def deinit(self):
        self.pan.enable(0)
        self.tilt.enable(0)


# Connect to WiFi
# 连接到 WiFi 网络
def Connect_WIFI(ID, PASSWORD):
    sta = network.WLAN(0)  # 创建 WLAN 对象，0 表示站模式 / Create WLAN object, 0 indicates station mode
    if sta.isconnected():  # 检查是否已连接 / Check if already connected
        sta.disconnect()   # 如果已连接，则断开连接 / Disconnect if already connected
        time.sleep(1)      # 等待 1 秒 / Wait for 1 second

    sta.connect(ID, PASSWORD)  # 连接到指定的 WiFi 网络 / Connect to the specified WiFi network
    # 查看是否连接成功 / Check if connection is successful
    while sta.ifconfig()[0] == '0.0.0.0':  # 如果 IP 地址为 '0.0.0.0'，表示未连接 / If IP address is '0.0.0.0', it means not connected
        time.sleep(1)                      # 每秒检查一次 / Check every second

    print(sta.ifconfig()[0])  # 打印获取到的 IP 地址 / Print the obtained IP address

    return sta.isconnected()  # 返回连接状态 / Return connection status

# RTSP Server class
# RTSP 服务器类
class RtspServer:
    def __init__(self, session_name="video", port=8554, video_type=mm.multi_media_type.media_h264,
                 enable_audio=False, sensor=None, initMediaManager=False):
        self.session_name = session_name  # 会话名称 / Session name
        self.video_type = video_type      # 视频类型：H.264/H.265 / Video type: H.264/H.265
        self.enable_audio = enable_audio  # 是否启用音频 / Whether to enable audio
        self.port = port                  # RTSP 端口号 / RTSP port number
        self.rtspserver = mm.rtsp_server()  # 实例化 RTSP 服务器 / Instantiate RTSP server
        self.venc_chn = VENC_CHN_ID_0     # VENC 通道 / VENC channel
        self.start_stream = False         # 是否启动推流线程 / Whether to start the streaming thread
        self.runthread_over = False       # 推流线程是否已结束 / Whether the streaming thread has finished
        self.sensor = sensor              # 传感器对象 / Sensor object
        self.initMediaManager = initMediaManager  # 是否初始化媒体管理器 / Whether to initialize media manager

    # Start the RTSP server
    # 启动 RTSP 服务器
    def start(self):
        # 初始化推流 / Initialize stream
        self._init_stream()
        self.rtspserver.rtspserver_init(self.port)  # 初始化 RTSP 服务器，指定端口 / Initialize RTSP server with specified port
        # 创建会话 / Create session
        self.rtspserver.rtspserver_createsession(self.session_name, self.video_type, self.enable_audio)
        # 启动 RTSP 服务器 / Start RTSP server
        self.rtspserver.rtspserver_start()
        self._start_stream()  # 启动推流 / Start streaming

        # 启动推流线程 / Start streaming thread
        self.start_stream = True
        _thread.start_new_thread(self._do_rtsp_stream, ())  # 创建新线程运行推流函数 / Create a new thread to run the streaming function

    # Stop the RTSP server
    # 停止 RTSP 服务器
    def stop(self):
        if self.start_stream == False:  # 如果推流未启动，直接返回 / If streaming hasn’t started, return directly
            return
        # 等待推流线程退出 / Wait for the streaming thread to exit
        self.start_stream = False
        while not self.runthread_over:  # 循环等待线程结束 / Loop until the thread ends
            sleep(0.1)                 # 每 0.1 秒检查一次 / Check every 0.1 seconds
        self.runthread_over = False    # 重置线程结束标志 / Reset thread completion flag

        # 停止推流 / Stop streaming
        self._stop_stream()
        self.rtspserver.rtspserver_stop()  # 停止 RTSP 服务器 / Stop RTSP server
        # self.rtspserver.rtspserver_destroysession(self.session_name)  # 销毁会话（已注释） / Destroy session (commented out)
        self.rtspserver.rtspserver_deinit()  # 反初始化 RTSP 服务器 / Deinitialize RTSP server

    # Get the RTSP URL
    # 获取 RTSP 地址
    def get_rtsp_url(self):
        return self.rtspserver.rtspserver_getrtspurl(self.session_name)  # 返回 RTSP 地址 / Return RTSP URL

    # Initialize the stream
    # 初始化推流
    def _init_stream(self):
        # 设置视频分辨率（以下为可选分辨率，已注释部分为其他选项） / Set video resolution (commented sections are other options)
        # width = 1280
        # height = 720
        # width = 640
        # height = 360
        # width = 1920
        # height = 1080
        width = 640   # 当前宽度 / Current width
        height = 480  # 当前高度 / Current height
        # width = 384
        # height = 216

        width = ALIGN_UP(width, 16)  # 将宽度对齐到 16 的倍数 / Align width to a multiple of 16
        # 初始化传感器 / Initialize sensor
        self.sensor = Sensor()       # 创建传感器对象 / Create sensor object
        self.sensor.reset()          # 重置传感器 / Reset sensor

        self.sensor.set_framesize(width=width, height=height, alignment=12, chn=CAM_CHN_ID_0)  # 设置帧大小 / Set frame size
        self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)  # 设置像素格式为 YUV420SP / Set pixel format to YUV420SP

        self.sensor.set_framesize(width=width, height=height, chn=CAM_CHN_ID_1)  # 设置显示通道帧大小 / Set display channel frame size
        self.sensor.set_pixformat(Sensor.RGB565, chn=CAM_CHN_ID_1)  # 设置显示通道像素格式为 RGB565 / Set display channel pixel format to RGB565

        # 实例化视频编码器 / Instantiate video encoder
        self.encoder = Encoder()     # 创建编码器对象 / Create encoder object
        self.encoder.SetOutBufs(self.venc_chn, 8, width, height)  # 设置输出缓冲区 / Set output buffers
        # 绑定相机和 VENC（已注释，当前未使用） / Bind camera and VENC (commented out, not currently used)
        # self.link = MediaManager.link(self.sensor.bind_info()['src'], (VIDEO_ENCODE_MOD_ID, VENC_DEV_ID, self.venc_chn))

        self.link = None  # 初始化链接为 None / Initialize link as None
        # 初始化媒体管理器 / Initialize media manager
        Display.init(Display.ST7701, width=width, height=height, to_ide=True)
        MediaManager.init()  # 调用媒体管理器的初始化函数 / Call the media manager’s initialization function
        # 创建编码器 / Create encoder
        chnAttr = ChnAttrStr(self.encoder.PAYLOAD_TYPE_H264, self.encoder.H264_PROFILE_MAIN, width, height, bit_rate=100, dst_frame_rate=5, src_frame_rate=5)

        # 设置编码器属性：H.264 类型，主配置文件，宽度，高度 / Set encoder attributes: H.264 type, main profile, width, height
        self.encoder.Create(self.venc_chn, chnAttr)  # 创建编码器通道 / Create encoder channel

    # Start the stream
    # 启动推流
    def _start_stream(self):
        # 开始编码 / Start encoding
        self.encoder.Start(self.venc_chn)  # 启动编码器通道 / Start encoder channel
        # 启动相机 / Start camera
        self.sensor.run()  # 运行传感器 / Run sensor

    # Stop the stream
    # 停止推流
    def _stop_stream(self):
        # 停止相机 / Stop camera
        self.sensor.stop()  # 停止传感器 / Stop sensor
        # 解绑相机和 VENC / Unbind camera and VENC
        del self.link       # 删除链接对象 / Delete link object
        # 停止编码 / Stop encoding
        self.encoder.Stop(self.venc_chn)     # 停止编码器通道 / Stop encoder channel
        self.encoder.Destroy(self.venc_chn)  # 销毁编码器通道 / Destroy encoder channel
        # 清理缓冲区 / Clear buffer
        Display.deinit()
        MediaManager.deinit()  # 反初始化媒体管理器 / Deinitialize media manager

    # RTSP streaming thread
    # RTSP 推流线程
    def _do_rtsp_stream(self):
        try:
            streamData = StreamData()  # 创建流数据对象 / Create stream data object
            frame_info = k_video_frame_info()  # 创建视频帧信息对象 / Create video frame info object

            while self.start_stream:  # 当推流标志为 True 时循环 / Loop while streaming flag is True
                # 捕获一帧 / Capture a frame
                rtsp_show_img = self.sensor.snapshot(chn=CAM_CHN_ID_0)  # 从传感器获取一帧图像 / Get one frame from sensor


                if rtsp_show_img == -1:  # 如果捕获失败，跳过本次循环 / If capture fails, skip this iteration
                    continue

                display_img = self.sensor.snapshot(chn=CAM_CHN_ID_1)
                if display_img != -1:
                    Display.show_image(display_img)

                frame_info.v_frame.width = rtsp_show_img.width()    # 设置帧宽度 / Set frame width
                frame_info.v_frame.height = rtsp_show_img.height()  # 设置帧高度 / Set frame height
                frame_info.v_frame.pixel_format = Sensor.YUV420SP   # 设置像素格式 / Set pixel format
                frame_info.pool_id = rtsp_show_img.poolid()      # 设置缓冲池 ID / Set buffer pool ID
                frame_info.v_frame.phys_addr[0] = rtsp_show_img.phyaddr()  # 设置第一平面的物理地址 / Set physical address of the first plane

                # 根据图像大小设置第二平面的物理地址 / Set the physical address of the second plane based on image size
                if rtsp_show_img.width() == 800 and rtsp_show_img.height() == 480:
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + \
                        frame_info.v_frame.width * frame_info.v_frame.height + 1024
                elif rtsp_show_img.width() == 1920 and rtsp_show_img.height() == 1080:
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + \
                        frame_info.v_frame.width * frame_info.v_frame.height + 3072
                elif rtsp_show_img.width() == 640 and rtsp_show_img.height() == 360:
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + \
                        frame_info.v_frame.width * frame_info.v_frame.height + 3072
                else:
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + \
                        frame_info.v_frame.width * frame_info.v_frame.height

                # 将帧发送到编码器 / Send the frame to the encoder
                self.encoder.SendFrame(self.venc_chn, frame_info)
                self.encoder.GetStream(self.venc_chn, streamData)  # 获取一帧流数据 / Get a frame of stream data

                # 将编码数据发送到 RTSP 服务器 / Send encoded data to the RTSP server
                for pack_idx in range(0, streamData.pack_cnt):  # 遍历数据包 / Iterate over data packets
                    stream_data = bytes(uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx]))
                    # 将数据转换为字节流 / Convert data to byte stream
                    # print("stream size: ", streamData.data_size[pack_idx], "stream type: ", streamData.stream_type[pack_idx])
                    self.rtspserver.rtspserver_sendvideodata(self.session_name, stream_data,
                                                             streamData.data_size[pack_idx], 1000)
                    # 发送视频数据到 RTSP 服务器 / Send video data to RTSP server

                self.encoder.ReleaseStream(self.venc_chn, streamData)  # 释放一帧流数据 / Release a frame of stream data

                ######################################

                gc.collect()         # 垃圾回收，释放内存 / Garbage collection to free memory
                time.sleep_us(10)    # 延时 10 微秒 / Delay for 10 microseconds
                os.exitpoint()       # 检查退出点 / Check exit point

        except BaseException as e:
            print(f"Exception {e}")  # 捕获并打印异常 / Catch and print exceptions
        finally:
            self.runthread_over = True  # 设置线程结束标志 / Set thread completion flag
            # 停止 RTSP 服务器 / Stop RTSP server
            self.stop()

        self.runthread_over = True  # 确保线程结束标志为 True / Ensure thread completion flag is True

if __name__ == "__main__":
    print("[WIFI] 连接网络中 Connecting to network ...")  # 提示正在连接网络 / Indicate network connection in progress
    # 连接 WiFi 网络 / Connect to WiFi network
    isConnected = Connect_WIFI("程源的iPhone", "qweasdf1234")  # 使用指定 ID 和密码连接 / Connect using specified ID and password
    if isConnected:
        print("[WIFI] 网络连接成功 Network connection successful")  # 连接成功提示 / Connection successful message
    else:
        import sys
        print("[WIFI] 网络连接失败 Network connection failed! Please check the configuration")
        # 连接失败提示 / Connection failed message
        time.sleep_ms(10)  # 延时 10 毫秒 / Delay for 10 milliseconds
        sys.exit()         # 退出程序 / Exit program

    print("[RTSP] Starting ...")  # 提示 RTSP 启动 / Indicate RTSP starting
    time.sleep(1)                # 延时 1 秒 / Delay for 1 second

    # 创建 RTSP 服务器对象 / Create RTSP server object
    rtspserver = RtspServer()
    # 启动 RTSP 服务器 / Start RTSP server
    rtspserver.start()
    # 打印 RTSP 地址 / Print RTSP URL
    rtsp_address = rtspserver.get_rtsp_url()
    ptz = PTZTimer()

    def ptz_loop():
        print("[PTZ] Timer started, move interval: 10 minutes")
        while True:
            result = ptz.update()
            if result:
                index, pan_ms, tilt_ms = result
                print("[PTZ] Move to preset:", index, "pan:", pan_ms, "tilt:", tilt_ms)
            time.sleep_ms(100)

    _thread.start_new_thread(ptz_loop, ())
    print("[RTSP] Started successfully, address:", rtsp_address)  # 启动成功并显示地址 / Started successfully and show address

    # 推流 60 秒 / Stream for 60 seconds
    while True:
        time.sleep_ms(10)  # 每 10 毫秒循环一次 / Loop every 10 milliseconds
    # 停止 RTSP 服务器 / Stop RTSP server
    rtspserver.stop()
    print("done")  # 提示完成 / Indicate completion
