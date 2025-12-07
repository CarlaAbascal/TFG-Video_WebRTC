import asyncio
import json
import logging

import cv2  # solo por si quieres pruebas locales, no es obligatorio
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay

logging.basicConfig(level=logging.INFO)

pcs_publishers = set()
pcs_viewers = set()

relay = MediaRelay()
relay_video_track = None  # aquí guardaremos el vídeo que viene del script


# ---------------------------
# RUTAS HTTP BÁSICAS
# ---------------------------
async def index(request):
    # Sirve la página del visor
    return web.FileResponse("client.html")


# ---------------------------
# PUBLICADOR (SCRIPT) → /publish_offer
# ---------------------------
async def publish_offer(request):
    """
    El SCRIPT llama aquí:
      - Envía su SDP offer
      - El servidor responde con answer
      - El script queda conectado como PUBLISHER
    """
    global relay_video_track

    params = await request.json()
    logging.info("Offer de publisher recibida")

    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs_publishers.add(pc)
    logging.info("Nuevo RTCPeerConnection para publisher (%s)", id(pc))

    @pc.on("track")
    async def on_track(track):
        global relay_video_track
        logging.info("Track recibido del publisher: %s", track.kind)

        if track.kind == "video":
            # Usamos MediaRelay para poder enviar este track a varios viewers
            relay_video_track = relay.subscribe(track)
            logging.info("Track de vídeo del publisher listo para reenviar")

        @track.on("ended")
        async def on_ended():
            logging.info("Track del publisher finalizado")
            # Opcional: podrías poner relay_video_track = None

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    logging.info("Enviando answer al publisher")

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
            }
        ),
    )


# ---------------------------
# VIEWER (NAVEGADOR/MÓVIL) → /viewer_offer
# ---------------------------
async def viewer_offer(request):
    global relay_video_track

    try:
        # Verificar que ya haya vídeo del publisher
        if relay_video_track is None:
            return web.Response(
                status=503,
                content_type="application/json",
                text=json.dumps({
                    "error": "No hay vídeo disponible todavía. Asegúrate de que el publisher está conectado."
                }),
            )

        params = await request.json()
        logging.info("Offer de viewer recibida")

        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        pc = RTCPeerConnection()
        pcs_viewers.add(pc)
        logging.info("Nuevo RTCPeerConnection para viewer (%s)", id(pc))

        # Añadimos el track de vídeo que viene del publisher
        pc.addTrack(relay_video_track)

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        logging.info("Enviando answer al viewer")

        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
            }),
        )

    except Exception as e:
        logging.exception("ERROR EN viewer_offer:")
        return web.Response(
            status=500,
            content_type="application/json",
            text=json.dumps({"error": str(e)}),
        )




# ---------------------------
# LIMPIEZA OPCIONAL
# ---------------------------
async def on_shutdown(app):
    coros = []
    for pc in list(pcs_publishers) + list(pcs_viewers):
        coros.append(pc.close())
    await asyncio.gather(*coros)
    pcs_publishers.clear()
    pcs_viewers.clear()


# ---------------------------
# ARRANQUE DE LA APP
# ---------------------------
app = web.Application()
app.on_shutdown.append(on_shutdown)

app.router.add_get("/", index)
app.router.add_post("/publish_offer", publish_offer)
app.router.add_post("/viewer_offer", viewer_offer)

if __name__ == "__main__":
    web.run_app(app, port=8080)
