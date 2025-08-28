from fastapi import FastAPI, File, UploadFile, Form, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import base64
import requests
import io
from PIL import Image
from dotenv import load_dotenv
import os
import logging

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Load environment variables ----------------
load_dotenv()

# ✅ Define app once
app = FastAPI()

templates = Jinja2Templates(directory="templates")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set in the .env file")


# ---------------- Root Route ----------------
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------- Upload & Query Route ----------------
@app.post("/upload_and_query")
async def upload_and_query(
    image: UploadFile = File(None),  # optional
    query: str = Form(None)          # optional
):
    try:
        if not image and not query:
            raise HTTPException(status_code=400, detail="Provide at least an image or a query.")

        encoded_image = None
        mime_type = None

        # Handle image if uploaded
        if image:
            image_content = await image.read()
            if not image_content:
                raise HTTPException(status_code=400, detail="Uploaded image is empty.")

            encoded_image = base64.b64encode(image_content).decode("utf-8")

            # Validate image format
            try:
                img = Image.open(io.BytesIO(image_content))
                img.verify()
            except Exception as e:
                logger.error(f"Invalid image format: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")

            # Detect MIME type
            ext = image.filename.split(".")[-1].lower()
            mime_type = "image/png" if ext == "png" else "image/jpeg"

        # Build messages dynamically
        content = []
        if query:
            content.append({"type": "text", "text": query})
        if encoded_image:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"}
            })

        messages = [{"role": "user", "content": content}]

        # Function to make Groq API requests
        def make_api_request(model):
            try:
                response = requests.post(
                    GROQ_API_URL,
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 1000
                    },
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    timeout=60
                )
                return response
            except Exception as e:
                logger.error(f"Request failed for model {model}: {str(e)}")
                return None

        # ✅ Use Groq models
        scout_response = make_api_request("meta-llama/llama-4-scout-17b-16e-instruct")
        maverick_response = make_api_request("meta-llama/llama-4-maverick-17b-128e-instruct")

        responses = {"llama": "⚠ No response", "llava": "⚠ No response"}

        for key, response in [
            ("llama", scout_response),
            ("llava", maverick_response)
        ]:
            if response and response.status_code == 200:
                result = response.json()
                try:
                    answer = result["choices"][0]["message"]["content"]
                except KeyError:
                    logger.error(f"Unexpected response format: {result}")
                    answer = f"Unexpected response format: {result}"
                logger.info(f"Processed response from {key}: {answer[:100]}...")
                responses[key] = answer
            elif response:
                logger.error(f"Error from {key}: {response.status_code} - {response.text}")
                responses[key] = f"Error {response.status_code}: {response.text}"

        return JSONResponse(status_code=200, content=responses)

    except HTTPException as he:
        logger.error(f"HTTP Exception: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


# ---------------- Run Server ----------------
if __name__ == "__main__":
    import uvicorn
    # ✅ make sure app is used here
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True) 