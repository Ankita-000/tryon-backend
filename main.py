from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
import cloudinary
import cloudinary.uploader
import os
import tempfile
import requests
import base64
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


def try_space(person_path, garment_path, description, space_name):
    """Try a specific HuggingFace space"""
    from gradio_client import Client, handle_file
    client = Client(space_name)
    result = client.predict(
        dict={
            "background": handle_file(person_path),
            "layers": [],
            "composite": None
        },
        garm_img=handle_file(garment_path),
        garment_des=description,
        is_checked=True,
        is_checked_crop=False,
        denoise_steps=30,
        seed=42,
        api_name="/tryon"
    )
    return result


def extract_image_path(result):
    """Extract image path from any result format"""
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, str) and os.path.exists(item):
                return item
            elif isinstance(item, dict):
                p = item.get('path') or item.get('url') or item.get('value')
                if p: return p
    elif isinstance(result, str):
        return result
    elif isinstance(result, dict):
        return result.get('path') or result.get('url')
    return None


@app.post("/tryon")
async def virtual_tryon(
    person_image: UploadFile = File(...),
    garment_url: str = Form(...),
    garment_description: str = Form(...)
):
    try:
        # Save person image
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            contents = await person_image.read()
            tmp.write(contents)
            person_tmp_path = tmp.name

        # Download garment image
        garment_response = requests.get(garment_url, timeout=15)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp2:
            tmp2.write(garment_response.content)
            garment_tmp_path = tmp2.name

        # Try multiple spaces in order until one works
        spaces = [
            "franciszzj/Leffa",
            "levihsu/OOTDiffusion",
            "yisol/IDM-VTON",
            "Nymbo/Virtual-Try-On",
        ]

        result_image_path = None
        last_error = ""

        for space in spaces:
            try:
                print(f"Trying space: {space}")
                result = try_space(
                    person_tmp_path,
                    garment_tmp_path,
                    garment_description,
                    space
                )
                result_image_path = extract_image_path(result)
                if result_image_path:
                    print(f"Success with space: {space}")
                    break
            except Exception as e:
                last_error = str(e)
                print(f"Space {space} failed: {e}")
                continue

        if not result_image_path:
            return {
                "success": False,
                "error": f"All spaces unavailable. Last error: {last_error}"
            }

        # Upload result to Cloudinary
        upload_response = cloudinary.uploader.upload(result_image_path)
        result_url = upload_response["secure_url"]

        # Cleanup
        try:
            os.unlink(person_tmp_path)
            os.unlink(garment_tmp_path)
        except:
            pass

        return {"success": True, "result_url": result_url}

    except Exception as e:
        return {"success": False, "error": str(e)}