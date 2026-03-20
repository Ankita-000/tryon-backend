from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
from gradio_client import Client, handle_file
from huggingface_hub import login
import cloudinary
import cloudinary.uploader
import os
import tempfile
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

@app.get("/")
def root():
    return {"status": "Virtual Try-On Backend is running!"}

@app.post("/tryon")
async def virtual_tryon(
    person_image: UploadFile = File(...),
    garment_url: str = Form(...),
    garment_description: str = Form(...)
):
    try:
        # Save person image temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            contents = await person_image.read()
            tmp.write(contents)
            person_tmp_path = tmp.name

        # Download garment image
        garment_response = requests.get(garment_url)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp2:
            tmp2.write(garment_response.content)
            garment_tmp_path = tmp2.name

        # Call HuggingFace IDM-VTON (FREE)
          login(token=os.getenv("HF_TOKEN"))
        client = Client("yisol/IDM-VTON")

        result = client.predict(
            dict={
                "background": handle_file(person_tmp_path),
                "layers": [],
                "composite": None
            },
            garm_img=handle_file(garment_tmp_path),
            garment_des=garment_description,
            is_checked=True,
            is_checked_crop=False,
            denoise_steps=30,
            seed=42,
            api_name="/tryon"
        )

        result_image_path = result[0]

        # Upload result to Cloudinary
        upload_response = cloudinary.uploader.upload(result_image_path)
        result_url = upload_response["secure_url"]

        os.unlink(person_tmp_path)
        os.unlink(garment_tmp_path)

        return {"success": True, "result_url": result_url}

    except Exception as e:
        return {"success": False, "error": str(e)}