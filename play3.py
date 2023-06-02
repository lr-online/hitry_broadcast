import wave
import asyncio

import pyaudio
from loguru import logger

from main import IDMP, idmp_conf


def play_wav_file_on_mac(wav_path):
    # Set chunk size of 1024 samples per data frame
    chunk = 1024

    # Open the sound file
    wf = wave.open(wav_path, "rb")

    # Create an interface to PortAudio
    p = pyaudio.PyAudio()

    # Open a .Stream object to write the WAV file to
    # 'output = True' indicates that the sound will be played rather than recorded
    stream = p.open(
        format=p.get_format_from_width(wf.getsampwidth()),
        channels=wf.getnchannels(),
        rate=wf.getframerate(),
        output=True,
    )

    # Read data in chunks
    data = wf.readframes(chunk)

    # Play the sound by writing the audio data to the stream
    while data:
        stream.write(data)
        data = wf.readframes(chunk)

    # Close and terminate the stream
    stream.close()
    p.terminate()


def play_pcm_file_on_mac(pcm_path):
    with open(pcm_path, "rb") as f:
        data = f.read()

    # 创建PyAudio对象
    p = pyaudio.PyAudio()
    stream = p.open(
        format=p.get_format_from_width(4),
        channels=1,  # 声道数
        rate=48000,  # 采样率
        # frames_per_buffer=4096,
        output=True,
    )

    # 播放PCM数据
    stream.write(data)

    # 停止数据流
    stream.stop_stream()
    stream.close()

    # 关闭PyAudio
    p.terminate()


async def play_pcm_file_on_hitry_speaker(pcm_path):
    async with IDMP(**idmp_conf) as idmp_server:
        task_id = await idmp_server.start_pcm_broadcast(
            sample_rate=48000,
            terminal_ids=[
                # "10138ae9993743e9a5b81ffe1c906165",  # 网红沙滩
                "2ec1ea90c7444bfead53dbf7cbd25270",  # 办公室
            ],
            to_all_terminal=False,
            is_strong_cur=True,
        )
        logger.info(f"开始广播任务：{task_id}")

        with open(pcm_path, "rb") as f:
            data = f.read()
        async with IDMP(**idmp_conf) as idmp_server:
            try:
                await idmp_server.send_pcm(
                    task_id=task_id,
                    chunk=data,
                )
                await idmp_server.stop_pcm_broadcast(task_id=task_id)

            except Exception as e:
                logger.warning(f"发送音频流失败：{e}")
            finally:
                logger.info(f"所有PCM连接接都已断开:{task_id}")


async def play_wav_file_on_hitry_speaker(wav_path):
    chunk = 1024 * 10
    wf = wave.open(wav_path, "rb")
    print(
        f"{wf.getframerate()/1000:.1f}k {wf.getsampwidth() * 8}bit {wf.getnchannels()}channel"
    )

    async with IDMP(**idmp_conf) as idmp_server:
        task_id = await idmp_server.start_pcm_broadcast(
            sample_rate=wf.getframerate(),
            terminal_ids=[
                "10138ae9993743e9a5b81ffe1c906165",  # 网红沙滩
                # "2ec1ea90c7444bfead53dbf7cbd25270",  # 办公室
            ],
            to_all_terminal=False,
            is_strong_cur=True,
        )
        logger.info(f"开始广播任务：{task_id}")

        try:
            data = wf.readframes(chunk)
            while data:
                await idmp_server.send_pcm(
                    task_id=task_id,
                    chunk=data,
                )
                await asyncio.sleep(0.1)
                data = wf.readframes(chunk)

        except Exception as e:
            logger.error(f"发送音频流失败：{e}", exc_info=True)
        finally:
            await asyncio.sleep(3)
            await idmp_server.stop_pcm_broadcast(task_id=task_id)
            logger.info(f"所有PCM连接接都已断开:{task_id}")


async def play_mp3_file_on_hitry_speaker(mp3_file):
    async with IDMP(**idmp_conf) as idmp_server:
        task_id = await idmp_server.start_pcm_broadcast(
            sample_rate=48000,
            terminal_ids=["10138ae9993743e9a5b81ffe1c906165"],
            to_all_terminal=False,
            is_strong_cur=True,
        )
        logger.info(f"开始广播任务：{task_id}")

        with open(mp3_file, "rb") as f:
            data = f.read()
        async with IDMP(**idmp_conf) as idmp_server:
            try:
                await idmp_server.send_pcm(
                    task_id=task_id,
                    chunk=data,
                )
                await idmp_server.stop_pcm_broadcast(task_id=task_id)

            except Exception as e:
                logger.warning(f"发送音频流失败：{e}")
            finally:
                logger.info(f"所有PCM连接接都已断开:{task_id}")


if __name__ == "__main__":
    # asyncio.run(play_pcm_file_on_hitry_speaker("good_3248.pcm"))
    # play_pcm_file_on_mac("./good_3248.pcm")
    # play_wav_file_on_mac("/Users/liangrui/Desktop/ddd.wav")
    asyncio.run(
        play_wav_file_on_hitry_speaker(
            "/Users/liangrui/PycharmProjects/hitry_broadcast_demo/wav/ed9fe8ef7d91493fa24ec612152092df.wav"
        )
    )
    # asyncio.run(play_wav_file_on_hitry_speaker("/Users/liangrui/Downloads/test.wav"))
