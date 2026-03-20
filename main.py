from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
import cloudinary
import cloudinary.uploader
import os
import tempfile
import requests
import time
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
        FAL_KEY = os.getenv("FAL_KEY")

        # Save person image and upload to Cloudinary to get URL
        contents = await person_image.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(contents)
            person_tmp_path = tmp.name

        person_upload = cloudinary.uploader.upload(person_tmp_path)
        person_url = person_upload["secure_url"]

        # Submit job to fal.ai
        response = requests.post(
            "https://queue.fal.run/fashn/tryon/v1.6",
            headers={
                "Authorization": f"Key {FAL_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model_image": person_url,
                "garment_image": garment_url,
                "category": "one-pieces",
                "mode": "balanced",
                "garment_photo_type": "auto",
                "nsfw_filter": True
            },
            timeout=30
        )

        data = response.json()
        print("fal.ai submit:", data)

        request_id = data.get("request_id")
        if not request_id:
            return {"success": False, "error": f"Submit failed: {data}"}

        # Poll for result every 5 seconds
        for i in range(30):
            time.sleep(5)

            status_resp = requests.get(
                f"https://queue.fal.run/fashn/tryon/v1.6/requests/{request_id}/status",
                headers={"Authorization": f"Key {FAL_KEY}"},
                timeout=15
            )
            status_data = status_resp.json()
            print(f"Poll {i+1}: {status_data.get('status')}")

            if status_data.get("status") == "COMPLETED":
                result_resp = requests.get(
                    f"https://queue.fal.run/fashn/tryon/v1.6/requests/{request_id}",
                    headers={"Authorization": f"Key {FAL_KEY}"},
                    timeout=15
                )
                result_data = result_resp.json()
                print("Result:", result_data)

                images = result_data.get("images", [])
                if images:
                    result_image_url = images[0].get("url") if isinstance(images[0], dict) else images[0]
                else:
                    result_image_url = result_data.get("image", {}).get("url")

                if not result_image_url:
                    return {"success": False, "error": f"No image in result: {result_data}"}

                upload_response = cloudinary.uploader.upload(result_image_url)
                result_url = upload_response["secure_url"]

                try:
                    os.unlink(person_tmp_path)
                except:
                    pass

                return {"success": True, "result_url": result_url}

            elif status_data.get("status") == "FAILED":
                return {"success": False, "error": "fal.ai processing failed"}

        return {"success": False, "error": "Timeout — took too long"}

    except Exception as e:
        return {"success": False, "error": str(e)}