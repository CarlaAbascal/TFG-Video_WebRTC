import asyncio
import cv2
import aiohttp
from av import VideoFrame
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack


SERVER_URL = "http://localhost:8080"   # luego será "http://TU_IP_PUBLICA:8080"


class CameraStream(VideoStreamTrack):
    """
    Track de vídeo que lee de la webcam (o puedes cambiar a RTSP, etc.)
    """
    def __init__(self, camera_index=0):
        super().__init__()
        self.cap = cv2.VideoCapture(camera_index)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        ret, frame = self.cap.read()
        if not ret:
            # Si falla la lectura, espera un poco y reintenta
            await asyncio.sleep(0.1)
            return await self.recv()

        # Opcional: espejar
        frame = cv2.flip(frame, 1)

        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


async def run_publisher():
    pc = RTCPeerConnection()

    # Añadimos nuestra cámara como track de vídeo
    camera = CameraStream()
    pc.addTrack(camera)

    # Creamos la SDP offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # Enviamos la offer al servidor
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{SERVER_URL}/publish_offer",
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"Error al enviar offer: {resp.status} {text}")
                return

            answer = await resp.json()

    # Configuramos la answer que devuelve el servidor
    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
    )

    print("Publisher conectado. Enviando vídeo al servidor...")

    # Mantener el script vivo
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Detenido por el usuario")
    finally:
        await pc.close()


if __name__ == "__main__":
    asyncio.run(run_publisher())
