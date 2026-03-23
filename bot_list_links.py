import os
import asyncio
import discord
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse

# Token via variável de ambiente (não comitar token no código)
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    # Não lançar erro automático para permitir execução local sem token,
    # mas endpoints que dependem do bot irão falhar com mensagem clara.
    print("⚠️ Variável DISCORD_TOKEN não definida. Defina-a para conectar ao Discord.")

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


async def coletar_links():
    if TOKEN is None:
        raise RuntimeError("DISCORD_TOKEN não definido")

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
    if TOKEN is None:
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


@app.get("/links")
async def get_links(refresh: bool = False):
    path = "links_dos_filmes.html"

    # opcional: forçar coleta antes de servir (use /links?refresh=true)
    if refresh:
        if TOKEN is None:
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
                print(f"Erro na coleta durante refresh: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    if os.path.exists(path):
        # retorna HTML inline no browser (sem forçar download)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=200)
    raise HTTPException(
        status_code=404,
        detail="Arquivo HTML não encontrado. Execute /collect ou /links?refresh=true primeiro.",
    )


@app.get("/status")
async def status():
    return {"connected": client.is_ready(), "collect_busy": _collect_lock.locked()}


# Inicializa o bot do Discord em background quando a FastAPI sobe
@app.on_event("startup")
async def startup_event():
    if TOKEN is None:
        print("⚠️ Token ausente: o bot Discord não será conectado.")
        return
    loop = asyncio.get_event_loop()
    # Inicia o cliente em background (client.start é uma coroutine longa)
    loop.create_task(client.start(TOKEN))
    print("🔌 Iniciando conexão do bot Discord em background...")


@app.on_event("shutdown")
async def shutdown_event():
    if client.is_ready():
        await client.close()
    print("⏹️ Aplicação finalizando, bot desconectado se estava conectado.")
