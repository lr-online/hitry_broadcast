import uuid
import wave
from typing import Awaitable, List, Optional

import aiohttp
from tornado.websocket import WebSocketHandler
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, Application
from tornado.httputil import url_concat

from loguru import logger

idmp_conf = dict(
    host="10.17.21.115",
    port=9000,
    app_key="a4062b34dea9bae1",
    app_secret="40b92ba6607c47a3ba5027af9f9deb1e",
)


def pcm_to_wav_use_ffmpeg(pcm_file: str, wav_file: str):
    import subprocess

    command = f"ffmpeg -i {pcm_file} -acodec pcm_s16le -ac 1 -ar 48000 {wav_file}"

    try:
        subprocess.run(command, shell=True, check=True)
        return True
    except Exception as e:
        return False


class IDMP(object):
    # 智能数字化综合管理平台 Intelligent digital management platform

    token_cache_template = "ams:idmp:token:{}"
    play_permission_cache_template = "ams:idmp:playPermission:{}:{}"  # host, terminal
    token_cache = {}

    def __init__(self, host: str, port: int, app_key: str, app_secret: str):
        self.host = host
        self.port = port
        self.app_key = app_key
        self.app_secret = app_secret
        self.token = None
        self.terminals = {}
        self.partitions = {}

    async def __aenter__(self):
        await self.refresh_token()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def attach_token(self, method, **kwargs):
        if method == "GET":
            kwargs["params"] = kwargs.get("params") or {}
            kwargs["params"].update({"token": self.token})
        elif method == "POST":
            kwargs["data"] = kwargs["data"] or {}
            kwargs["data"].update({"token": self.token})
        return kwargs

    async def _request(self, url, method="GET", **kwargs):
        if "/OpenAPI/GetToken" not in url:
            kwargs = self.attach_token(method, **kwargs)
        if not url.startswith("http"):
            url = self.build_url(path=url)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3)
        ) as session:
            async with session.request(
                method=method,
                url=url,
                **kwargs,
            ) as resp:
                resp_body = await resp.text()
                logger.debug(f"{method} {url} {kwargs}-->{resp.status} {resp_body}")
                if resp.status >= 400:
                    await self.refresh_token()
                assert resp.status == 200, resp_body
                reply = await resp.json()
                assert reply.get("errno") == 0, reply.get("errmsg")
                return reply

    def cache_token(self, expire=1 * 3600):
        # 大华的token有效期是2小时，我们这里1小时刷新一次，避免token过期
        self.token_cache[self.app_key] = self.token
        logger.info(f"{self.app_key} 的token已缓存")

    async def refresh_token(self):
        self.token = self.token_cache.get(self.app_key)
        if self.token:
            logger.debug(f"token有缓存：{self.token}")
            return

        await self.request_token_from_idmp()
        self.cache_token()

    def build_url(self, path: str = "", query_string: dict = None):
        assert path.startswith("/"), f"path不合法：{path}"
        if query_string:
            path = url_concat(path, query_string)
        return f"http://{self.host}:{self.port}{path}"

    async def request_token_from_idmp(self):
        reply = await self._request(
            url="/OpenAPI/GetToken",
            method="GET",
            params={
                "appKey": self.app_key,
                "appSecret": self.app_secret,
            },
        )
        self.token = reply.get("result", {}).get("token")
        logger.debug(f"从IDMP服务获取到新的token:{self.token}")

    async def start_pcm_broadcast(
        self,
        sample_rate: int,
        terminal_ids: Optional[List[str]] = None,
        to_all_terminal: bool = True,
        is_strong_cur: bool = True,
    ):
        """
        发起实时语音广播
        :param sample_rate: 采样率
        :param terminal_ids: 终端编号
        :param to_all_terminal:目标终端为所有终端
        :param is_strong_cur:强切开发 False关闭、True开启
        :return:
        """
        reply = await self._request(
            url="/OpenAPI/Broadcast",
            method="GET",
            params={
                "terminalIds": ",".join(terminal_ids) if terminal_ids else "",
                "isAllTerminal": int(to_all_terminal),
                "isStrongCut": int(is_strong_cur),
                "sampleRate": sample_rate,
            },
        )
        task_id = reply.get("result", {}).get("taskId")
        # {'errno': 1, 'errmsg': '无操作权限', 'result': None}
        logger.info(f"发起广播: {reply}")
        return task_id

    async def stop_pcm_broadcast(self, task_id: int):
        """
        结束语音广播
        :param task_id:
        :return:
        """
        reply = await self._request(
            url="/OpenAPI/Broadcast_Stop",
            method="GET",
            params={
                "taskId": task_id,
            },
        )
        # {'errno': 0, 'errmsg': '', 'result': None}
        logger.info(f"结束广播: {reply}")

    async def send_pcm(self, task_id: str, chunk: bytes):
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3)
        ) as session:
            async with session.ws_connect(
                self.build_url(
                    "/OpenAPI/pcmData", {"token": self.token, "taskId": task_id}
                )
            ) as ws:
                logger.debug(f"send {len(chunk)} pcm data")
                await ws.send_bytes(chunk)


class BroadcastHandler(WebSocketHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_id = None

    def data_received(self, chunk: bytes) -> Optional[Awaitable[None]]:
        logger.info(f"data_received: {chunk}")
        return None

    # async def check_token(self):
    #     assert self.token, "Error.TOKEN_CANNOT_BE_NULL"

    async def open(self):
        if self.task_id is not None:
            raise Exception(f"当前已经有广播任务了 {self.task_id} ")
        logger.info(f"建立新的语音广播WebSocket连接:{self.request.remote_ip}")
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
            self.task_id = task_id
            logger.info(f"开始广播任务：{self.task_id}")
            self.pcm_cache = []

    async def on_message(self, message):
        self.pcm_cache.append(message)

    async def send_wav(self):
        pcm_data = b"".join(self.pcm_cache)
        message_id = uuid.uuid4().hex

        pcm_file = f"pcm/{message_id}.pcm"
        wav_file = f"wav/{message_id}.wav"

        # 保存音频流
        with open(pcm_file, "wb") as f:
            f.write(pcm_data)

        # 转换音频流
        success = pcm_to_wav_use_ffmpeg(pcm_file, wav_file)
        if not success:
            logger.warning(f"转换音频流失败")
            await self.write_message(f"转换音频流失败")
            return

        # 发送音频流
        try:
            async with IDMP(**idmp_conf) as idmp_server:
                with wave.open(wav_file, "rb") as wav_reader:
                    chunk = 1024 * 4
                    data = wav_reader.readframes(chunk)
                    while data:
                        await idmp_server.send_pcm(
                            task_id=self.task_id,
                            chunk=data,
                        )
                        data = wav_reader.readframes(chunk)

        except Exception as e:
            await self.write_message(f"发送音频流失败")
        finally:
            # # 删除pcm文件和wav文件
            # os.remove(pcm_file)
            # os.remove(wav_file)
            logger.info(f"发送音频流结束")

    def on_close(self):
        async def foo():
            await self.send_wav()
            async with IDMP(**idmp_conf) as idmp_server:
                await idmp_server.stop_pcm_broadcast(task_id=self.task_id)

            logger.info(f"所有PCM连接接都已断开:{self.task_id}")

        IOLoop.current().add_callback(foo)

    def check_origin(self, origin):
        return True  # 允许WebSocket的跨域请求


class MainHandler(RequestHandler):
    def get(self):
        self.render("index.html")


app = Application(
    [
        (r"/", MainHandler),
        (r"/OpenAPI/pcmData", BroadcastHandler),
    ],
    debug=True,
)

if __name__ == "__main__":
    port = 8000
    app.listen(port)
    logger.info(f"server start at http://127.0.0.1:{port}")
    IOLoop.current().start()
