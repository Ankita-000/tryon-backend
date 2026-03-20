from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
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

        # Try Nymbo Virtual Try-On space (very reliable & free)
        from gradio_client import Client, handle_file

        client = Client("Nymbo/Virtual-Try-On")

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

        # Handle different result formats
        result_image_path = None

        if isinstance(result, (list, tuple)):
            # Try first element
            for item in result:
                if isinstance(item, str) and os.path.exists(item):
                    result_image_path = item
                    break
                elif isinstance(item, dict) and 'path' in item:
                    result_image_path = item['path']
                    break
                elif isinstance(item, dict) and 'url' in item:
                    result_image_path = item['url']
                    break
        elif isinstance(result, str):
            result_image_path = result
        elif isinstance(result, dict):
            result_image_path = result.get('path') or result.get('url')

        if not result_image_path:
            return {"success": False, "error": f"Unexpected result format: {str(result)[:200]}"}

        # Upload to Cloudinary
        upload_response = cloudinary.uploader.upload(result_image_path)
        result_url = upload_response["secure_url"]

        # Clean up
        try:
            os.unlink(person_tmp_path)
            os.unlink(garment_tmp_path)
        except:
            pass

        return {"success": True, "result_url": result_url}

    except Exception as e:
        return {"success": False, "error": str(e)}