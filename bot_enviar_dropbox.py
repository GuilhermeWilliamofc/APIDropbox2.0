import os
import subprocess
import asyncio
import discord
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import dropbox
import requests

# Tokens via variáveis de ambiente (não comitar tokens no código)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Dropbox App info + Refresh token (definidos no ambiente)
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")

if not DISCORD_TOKEN:
    print("⚠️ DISCORD_TOKEN não definido. O bot Discord não será conectado.")

if not DROPBOX_APP_KEY or not DROPBOX_APP_SECRET or not DROPBOX_REFRESH_TOKEN:
    print("⚠️ Variáveis do Dropbox ausentes. Endpoint de upload Dropbox falhará sem elas.")

IGNORAR_CATEGORIAS = [
    "╭╼ 🌐Uploader Mode",
    "╭╼ 👥Chat",
    "╭╼ 💎ADM chat",
    "╭╼ 📫Welcome",
    "⭒⇆◁ ❚❚ ▷↻ ⭒ 🔊 ▂▃▅▉ 100%⭒",
]

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

client = discord.Client(intents=intents)

app = FastAPI()
_collect_lock = asyncio.Lock()


def limpar_nome(nome):
    return nome.replace("/", "-").replace("\\", "-").replace(":", "-")

# 🔹 Função para gerar access token usando refresh token
def obter_access_token():
    if not all([DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN]):
        raise RuntimeError("Variáveis do Dropbox não definidas corretamente.")

    url = "https://api.dropbox.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": DROPBOX_REFRESH_TOKEN,
        "client_id": DROPBOX_APP_KEY,
        "client_secret": DROPBOX_APP_SECRET
    }
    resp = requests.post(url, data=data)
    resp.raise_for_status()
    access_token = resp.json().get("access_token")
    if not access_token:
        raise RuntimeError("Falha ao obter access token do Dropbox")
    return access_token


async def coletar_links():
    links_por_categoria = {}

    for guild in client.guilds:
        for canal in guild.text_channels:
            if canal.name == "geral":
                continue

            if canal.category is None or canal.category.name in IGNORAR_CATEGORIAS:
                continue

            try:
                blocos = []
                bloco_atual = None

                async for mensagem in canal.history(limit=None, oldest_first=True):
                    tem_imagem = False
                    imagem_url = None

                    # 🔍 verifica imagem (capa)
                    for anexo in mensagem.attachments:
                        if (
                            anexo.content_type
                            and anexo.content_type.startswith("image")
                        ) or anexo.filename.endswith(
                            (".png", ".jpg", ".jpeg", ".webp")
                        ):
                            tem_imagem = True
                            imagem_url = anexo.url
                            break

                    # 🎬 se achou imagem → novo bloco
                    if tem_imagem:
                        bloco_atual = {
                            "capa": imagem_url,
                            "titulo": "",
                            "sinopse": "",
                            "videos": [],
                        }

                        # 🧠 extrai texto da mensagem
                        conteudo = mensagem.content.strip()

                        if conteudo:
                            linhas = conteudo.split("\n")
                            bloco_atual["titulo"] = linhas[0]
                            if len(linhas) > 1:
                                bloco_atual["sinopse"] = " ".join(linhas[1:])

                        blocos.append(bloco_atual)

                    # 🎥 vídeos
                    for anexo in mensagem.attachments:
                        if (
                            anexo.content_type
                            and anexo.content_type.startswith("video")
                        ) or anexo.filename.endswith((".mp4", ".mov", ".webm", ".mkv")):
                            if bloco_atual:
                                bloco_atual["videos"].append(f"[VIDEO]{anexo.filename}|{anexo.url}")

                links_salvos = set()
                for bloco in blocos:
                    links_salvos.update(bloco["videos"])

                if blocos:
                    categoria_nome = canal.category.name
                    canal_nome = canal.name

                    if categoria_nome not in links_por_categoria:
                        links_por_categoria[categoria_nome] = []

                    links_por_categoria[categoria_nome].append(
                        (canal.position, canal_nome, blocos)
                    )
            except Exception as e:
                print(f"⚠️ Erro no canal {canal.name}: {e}")

    links_por_canal = []
    for guild in client.guilds:
        for categoria in guild.categories:
            if categoria.name in IGNORAR_CATEGORIAS:
                continue
            if categoria.name in links_por_categoria:
                canais = sorted(links_por_categoria[categoria.name], key=lambda x: x[0])
                for _, canal_nome, blocos in canais:
                    links_por_canal.append(f"# {categoria.name} / {canal_nome}\n")

                    for bloco in blocos:

                        # 🖼️ capa
                        if bloco["capa"]:
                            links_por_canal.append(f"[CAPA]{bloco['capa']}\n")

                        # 🏷️ título
                        if bloco["titulo"]:
                            links_por_canal.append(f"[TITULO]{bloco['titulo']}\n")

                        # 📝 sinopse
                        if bloco["sinopse"]:
                            links_por_canal.append(f"[SINOPSE]{bloco['sinopse']}\n")

                        # 🎥 vídeos
                        for video in bloco["videos"]:
                            links_por_canal.append(video + "\n")

                        links_por_canal.append("\n")

    with open("links_dos_filmes.txt", "w", encoding="utf-8") as f:
        f.writelines(links_por_canal)

    print("✅ Coleta de links concluída!")

    gerar_html_videos("links_dos_filmes.txt", "links_dos_filmes.html")
    print("✅ HTML gerado: links_dos_filmes.html")
    await client.close()  # <---- encerra o bot após gerar o HTML


def gerar_html_videos(input_txt, output_txt):
    html_output = [
        "<!DOCTYPE html>\n",
        "<html>\n<head>\n<meta charset='utf-8'>\n",
        "<style>\n",
        "  body { font-family: Arial; background:#111; color:#eee; }\n",
        "  img.capa { border-radius:10px; margin-bottom:10px; width:100%; max-width:220px; height:auto; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }\n",
        "  @media (max-width: 600px) { img.capa { max-width: 140px; } }\n",
        "  .card { margin-bottom:30px; padding:10px; background:#1c1c1c; border-radius:12px; }\n",
        "  .album-btn { background-color: #333; color: white; padding: 10px; cursor: pointer; border: none; border-radius: 5px; margin-bottom: 5px; font-size: 16px; }\n",
        "  .album-btn:hover { background-color: #555; }\n",
        "  video { margin-top:10px; }\n",
        "</style>\n",
        "<script>\n",
        "function toggleAlbum(id) {\n",
        "  const div = document.getElementById(id);\n",
        "  div.style.display = div.style.display === 'none' ? 'block' : 'none';\n",
        "}\n",
        "</script>\n",
        "</head>\n<body>\n"
    ]

    with open(input_txt, "r", encoding="utf-8") as file:
        linhas = [linha.strip() for linha in file if linha.strip()]

    album_id = 0
    in_album = False

    for linha in linhas:
        if linha.startswith("#"):
            if in_album:
                html_output.append("</div>\n<br>\n")
            
            album_id += 1
            in_album = True
            titulo_album = linha[1:].strip()
            html_output.append(f"<button class='album-btn' onclick=\"toggleAlbum('album{album_id}')\">Mostrar/Ocultar {titulo_album}</button><br>\n")
            html_output.append(f"<div id='album{album_id}' style='display:none;' class='card'>\n")
            html_output.append(f"<h2>{titulo_album}</h2>\n")

        elif linha.startswith("[CAPA]"):
            capa = linha.replace("[CAPA]", "")
            html_output.append(f'<img src="{capa}" class="capa" loading="lazy">\n')

        elif linha.startswith("[TITULO]"):
            titulo = linha.replace("[TITULO]", "")
            html_output.append(f"<h3>{titulo}</h3>\n")

        elif linha.startswith("[SINOPSE]"):
            sinopse = linha.replace("[SINOPSE]", "")
            html_output.append(f"<p>{sinopse}</p>\n")

        elif linha.startswith("[VIDEO]"):
            partes = linha.replace("[VIDEO]", "").split("|", 1)
            if len(partes) == 2:
                nome, url = partes
            else:
                nome = "video.mp4"
                url = partes[0]
            
            html_output.append(f"<p>{nome}</p>\n")
            html_output.append(f'<video controls style="max-width:100%; height:auto;" preload="none">\n')
            html_output.append(f'    <source src="{url}">\n')
            html_output.append('    Seu navegador não suporta vídeo.\n')
            html_output.append("</video>\n<br><br>\n")

        elif linha.startswith("http"):
            html_output.append(f"<p>video.mp4</p>\n")
            html_output.append(f'<video controls style="max-width:100%; height:auto;" preload="none">\n')
            html_output.append(f'    <source src="{linha}">\n')
            html_output.append('    Seu navegador não suporta vídeo.\n')
            html_output.append("</video>\n<br><br>\n")

    if in_album:
        html_output.append("</div>\n")

    html_output.append("</body>\n</html>\n")

    with open(output_txt, "w", encoding="utf-8") as file:
        file.writelines(html_output)


@client.event
async def on_ready():
    print(f"✅ Bot conectado como {client.user}")


@app.post("/collect")
async def trigger_collect():
    if DISCORD_TOKEN is None:
        raise HTTPException(
            status_code=500, detail="DISCORD_TOKEN não definido no ambiente"
        )

    if not client.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Bot Discord não está conectado ainda. Aguarde inicialização.",
        )

    if _collect_lock.locked():
        return JSONResponse(
            {"status": "busy", "detail": "Coleta já em execução"}, status_code=202
        )

    async with _collect_lock:
        try:
            await coletar_links()
        except Exception as e:
            print(f"Erro na coleta: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "message": "Coleta finalizada, arquivos gerados"}


@app.post("/upload_dropbox")
async def upload_dropbox(
    path_local: str = "links_dos_filmes.html",
    caminho_dropbox: str = "/links_dos_filmes.html",
):
    if not all([DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN]):
        raise HTTPException(
            status_code=500, detail="Configuração do Dropbox incompleta"
        )

    if not os.path.exists(path_local):
        raise HTTPException(
            status_code=404, detail=f"Arquivo local não encontrado: {path_local}"
        )

    try:
        access_token = obter_access_token()
        dbx = dropbox.Dropbox(access_token)
        with open(path_local, "rb") as f:
            dbx.files_upload(
                f.read(), caminho_dropbox, mode=dropbox.files.WriteMode.overwrite
            )
    except Exception as e:
        print(f"Erro no upload Dropbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # tenta obter link compartilhado (se existir)
    try:
        links = dbx.sharing_list_shared_links(path=caminho_dropbox).links
        if links:
            link = links[0].url
            # prefira raw para embedding direto
            return {"status": "ok", "url": link.replace("?dl=0", "?raw=1")}
        else:
            return {
                "status": "ok",
                "message": "Upload concluído, link não encontrado automaticamente (crie no Dropbox se necessário).",
            }
    except Exception:
        return {
            "status": "ok",
            "message": "Upload concluído, não foi possível listar links (permissões).",
        }


@app.api_route("/collect_and_upload", methods=["GET", "POST"])
async def collect_and_upload():
    # combina coletar_links + upload_dropbox
    if DISCORD_TOKEN is None:
        raise HTTPException(
            status_code=500, detail="DISCORD_TOKEN não definido no ambiente"
        )

    if _collect_lock.locked():
        return JSONResponse(
            {"status": "busy", "detail": "Coleta já em execução"}, status_code=202
        )

    async with _collect_lock:
        try:
            await coletar_links()
        except Exception as e:
            print(f"Erro na coleta: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # após gerar HTML, faz upload
    return await upload_dropbox()


@app.get("/links")
async def get_links():
    path = "links_dos_filmes.html"
    if os.path.exists(path):
        return FileResponse(
            path, media_type="text/html", filename="links_dos_filmes.html"
        )
    raise HTTPException(
        status_code=404,
        detail="Arquivo HTML não encontrado. Execute /collect primeiro.",
    )


@app.get("/status")
async def status():
    return {"connected": client.is_ready(), "collect_busy": _collect_lock.locked()}


# Inicializa o bot do Discord em background quando a FastAPI sobe
@app.on_event("startup")
async def startup_event():
    if DISCORD_TOKEN is None:
        print("⚠️ Token ausente: o bot Discord não será conectado.")
        return
    loop = asyncio.get_event_loop()
    loop.create_task(client.start(DISCORD_TOKEN))
    print("🔌 Iniciando conexão do bot Discord em background...")


@app.on_event("shutdown")
async def shutdown_event():
    if client.is_ready():
        await client.close()
    print("⏹️ Aplicação finalizando, bot desconectado se estava conectado.")


# Roda o bot para gerar o arquivo txt
subprocess.run(["python", "bot_list_links.py"], check=True)

# Faz upload pro Dropbox usando refresh token
arquivo_local = "links_dos_filmes.html"
caminho_dropbox = "/links_dos_filmes.html"

try:
    access_token = obter_access_token()
    dbx = dropbox.Dropbox(access_token)
    with open(arquivo_local, "rb") as f:
        dbx.files_upload(f.read(), caminho_dropbox, mode=dropbox.files.WriteMode.overwrite)
    print("✅ Upload concluído para o Dropbox!")

    # Tenta pegar link existente
    links = dbx.sharing_list_shared_links(path=caminho_dropbox).links
    if links:
        link = links[0].url
        print("🔗 Link existente:", link.replace("?dl=0", "?raw=1"))
    else:
        print("ℹ️ Nenhum link encontrado — crie um manualmente no Dropbox.")
except Exception as e:
    print("⚠️ Erro no upload Dropbox:", e)
    print("   Verifique se as variáveis de ambiente estão corretas ou se há permissão.")
