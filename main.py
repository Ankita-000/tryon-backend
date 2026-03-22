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
        LIGHTX_KEY = os.getenv("LIGHTX_API_KEY")

        # Upload person image to Cloudinary to get a URL
        contents = await person_image.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(contents)
            person_tmp_path = tmp.name

        person_upload = cloudinary.uploader.upload(person_tmp_path)
        person_url = person_upload["secure_url"]
        print("Person URL:", person_url)

        # ✅ CORRECT LightX Virtual Try-On endpoint
        response = requests.post(
            "https://api.lightxeditor.com/external/api/v2/aivirtualtryon",
            headers={
                "Content-Type": "application/json",
                "x-api-key": LIGHTX_KEY
            },
            json={
                "imageUrl": person_url,
                "styleImageUrl": garment_url
            },
            timeout=30
        )

        data = response.json()
        print("LightX response:", data)

        # Get order ID
        order_id = data.get("body", {}).get("orderId")
        if not order_id:
            return {"success": False, "error": f"No order ID: {data}"}

        # Poll for result every 5 seconds (max 2 minutes)
        for i in range(24):
            time.sleep(5)

            status_resp = requests.post(
                "https://api.lightxeditor.com/external/api/v1/order-status",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": LIGHTX_KEY
                },
                json={"orderId": order_id},
                timeout=15
            )

            status_data = status_resp.json()
            status = status_data.get("body", {}).get("status")
            print(f"Poll {i+1}: {status}")

            if status == "active":
                result_image_url = status_data.get("body", {}).get("output")
                if not result_image_url:
                    return {"success": False, "error": "No output image"}

                # Upload to Cloudinary
                upload_response = cloudinary.uploader.upload(result_image_url)
                result_url = upload_response["secure_url"]

                try:
                    os.unlink(person_tmp_path)
                except:
                    pass

                return {"success": True, "result_url": result_url}

            elif status == "failed":
                return {"success": False, "error": "Processing failed"}

        return {"success": False, "error": "Timeout"}

    except Exception as e:
        return {"success": False, "error": str(e)}