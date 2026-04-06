import asyncio
import websockets
import pygame
import io
import socket
import logging
import os
import threading
import time
import subprocess
from datetime import datetime

#pip3 install pygame websockets pydub
# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Pygame音频初始化
pygame.mixer.init(
    frequency=16000,
    size=-16,
    channels=1,
    buffer=2048
)
pygame.mixer.set_num_channels(2)  # 增加通道数，支持重叠检测和播放

# 全局变量
is_connected = False
save_wav_file = True
wav_file_path = "audio_temp.wav"
is_playing = False  # 播放状态锁，防止重复播放


def get_local_ip():
    """获取鲁班猫4局域网IP"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip


def convert_webm_to_wav(webm_data):
    """将WebM数据转换为WAV数据"""
    try:
        from pydub import AudioSegment

        if len(webm_data) < 100:
            logging.error("WebM数据过短，无法转换")
            return None

        audio = AudioSegment.from_file(
            io.BytesIO(webm_data),
            format="webm",
            codec="opus"
        )
        # 标准化参数
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(2)
        audio = audio.set_sample_width(2)

        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav", codec="pcm_s16le")
        wav_io.seek(0)
        return wav_io.read()

    except Exception as e:
        logging.error(f"WebM转WAV失败: {e}", exc_info=True)
        return None


def play_and_delete_wav(file_path):
    """播放WAV文件，播放完成后删除"""
    global is_playing
    print(f"{file_path}")
    if not os.path.exists(file_path):
        logging.warning(f"文件不存在: {file_path}")
        is_playing = False
        return

    if is_playing:
        logging.info("已有音频正在播放，跳过")
        return

    is_playing = True

    try:
        # 加载并播放
        #sound = pygame.mixer.Sound(file_path)
        #channel = sound.play()

        #if channel:
            #logging.info(f"开始播放: {file_path}")
            # 等待播放完成
            #while channel.get_busy():
                #pygame.time.Clock().tick(10)
            #logging.info("播放完成")
        #else:
            #logging.error("无法获取音频通道")
        #pygame.mixer.music.load('audio_temp.wav')
        #logging.info(f"开始播放: {file_path}")
        #pygame.mixer.music.set_volume(0.8)
        #pygame.mixer.music.play()
        #while pygame.mixer.music.get_busy():
            #pygame.time.Clock().tick(10)
        result=subprocess.run(["aplay","-Dhw:2","audio_temp.wav"]
        ,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    except Exception as e:
        logging.error(f"播放失败: {e}", exc_info=True)

    finally:
        # 删除文件
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"已删除文件: {file_path}")
        except Exception as e:
            logging.error(f"删除文件失败: {e}")

        is_playing = False


def audio_player_loop():
    """后台线程：持续检测并播放audio_temp.wav"""
    while True:
        try:
            # 检测文件是否存在且不在播放中
            if os.path.exists(wav_file_path) and not is_playing:
                logging.info(f"检测到文件: {wav_file_path}")
                play_and_delete_wav(wav_file_path)
            else:
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.1)
        except Exception as e:
            logging.error(f"播放器循环错误: {e}")
            time.sleep(0.5)


async def handle_audio_stream(websocket):
    """处理WebSocket连接：接收WebM数据并转换为WAV文件"""
    global is_connected
    client_ip = websocket.remote_address[0]
    logging.info(f"客户端 {client_ip} 已连接")

    # 重置状态
    webm_buffer = io.BytesIO()
    is_connected = True

    try:
        while is_connected:
            try:
                # 接收前端的WebM分片数据
                webm_chunk = await asyncio.wait_for(websocket.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                logging.info(f"客户端 {client_ip} 断开连接")
                break

            if not isinstance(webm_chunk, bytes) or len(webm_chunk) == 0:
                logging.warning("接收无效数据，跳过")
                continue

            # 缓存WebM数据
            webm_buffer.write(webm_chunk)
            logging.debug(f"已缓存WebM分片，当前大小：{webm_buffer.tell()}字节")

    finally:
        is_connected = False

        # 连接断开，处理完整音频
        if webm_buffer.tell() > 0:
            webm_buffer.seek(0)
            webm_data = webm_buffer.read()

            # 转换为WAV
            wav_data = convert_webm_to_wav(webm_data)

            if wav_data:
                # 如果文件已存在，先删除（避免冲突）
                if os.path.exists(wav_file_path):
                    try:
                        os.remove(wav_file_path)
                        logging.info(f"删除旧文件: {wav_file_path}")
                    except Exception as e:
                        logging.error(f"删除旧文件失败: {e}")

                # 保存新WAV文件（触发播放器检测）
                with open(wav_file_path, "wb") as f:
                    f.write(wav_data)
                logging.info(f"已保存WAV文件: {wav_file_path} ({len(wav_data)}字节)")
            else:
                logging.error("转换失败，未生成WAV文件")

        logging.info("音频接收处理结束")


async def main():
    """启动WebSocket服务和音频播放器线程"""
    # 启动后台播放线程
    player_thread = threading.Thread(target=audio_player_loop, daemon=True)
    player_thread.start()
    logging.info("音频播放器后台线程已启动")

    local_ip = get_local_ip()
    async with websockets.serve(handle_audio_stream, "0.0.0.0", 8765):
        logging.info(f"鲁班猫4语音服务端已启动")
        logging.info(f"局域网地址：ws://{local_ip}:6109")
        await asyncio.Future()  # 持续运行


if __name__ == "__main__":
    # 检查依赖
    try:
        import pydub

        assert pygame.mixer.get_init(), "Pygame音频初始化失败"
    except (ImportError, AssertionError) as e:
        logging.error(f"基础依赖检查失败: {e}")
        logging.error("请执行以下命令安装依赖：")
        logging.error("1. pip install pygame pydub websockets")
        logging.error("2. sudo apt install ffmpeg -y (鲁班猫4 Debian系统)")
        exit(1)

    # 清理可能存在的旧文件
    if os.path.exists(wav_file_path):
        try:
            os.remove(wav_file_path)
            logging.info(f"清理旧文件: {wav_file_path}")
        except Exception as e:
            logging.error(f"清理旧文件失败: {e}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("服务端已手动停止")
    finally:
        # 等待当前播放完成
        while is_playing:
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        logging.info("Pygame音频资源已释放")
