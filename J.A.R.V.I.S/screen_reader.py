import os
import shutil
from datetime import datetime

import mss
from PIL import Image
import pytesseract
import cv2

from llm_local import ask_llm

from screen_memory import (
    remember_screenshot,
    get_last_screenshot,
    search_screenshots
)

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

SCREENSHOT_FILE = "screen_capture.png"
PROCESSED_FILE = "screen_processed.png"

HUD_STATUS_FILE = "hud_status.txt"
HUD_COMMAND_FILE = "hud_command.txt"
HUD_RESULT_FILE = "hud_result.txt"
HUD_VOICE_FILE = "voice_level.txt"

if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# ==========================
# HUD HELPERS
# ==========================
def write_hud(path, value):
    try:
        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(str(value))
    except Exception:
        pass


def update_hud(status=None, command=None, result=None, voice=None):
    if status is not None:
        write_hud(HUD_STATUS_FILE, status)

    if command is not None:
        write_hud(HUD_COMMAND_FILE, command)

    if result is not None:
        write_hud(HUD_RESULT_FILE, result)

    if voice is not None:
        write_hud(HUD_VOICE_FILE, voice)


def short_text(text, limit=180):
    text = str(text).replace("\n", " ").strip()

    if len(text) <= limit:
        return text

    return text[:limit - 3] + "..."


# ==========================
# SCREEN CAPTURE
# ==========================
def capture_screen(region="full"):
    update_hud(
        status="PROCESSING",
        command=f"Capturing screen: {region}",
        result="Taking screenshot...",
        voice="0.3"
    )

    with mss.mss() as sct:
        monitor = sct.monitors[1]

        left = monitor["left"]
        top = monitor["top"]
        width = monitor["width"]
        height = monitor["height"]

        if region == "center":
            crop = {
                "left": left + int(width * 0.18),
                "top": top + int(height * 0.08),
                "width": int(width * 0.64),
                "height": int(height * 0.78),
            }

        elif region == "terminal":
            crop = {
                "left": left + int(width * 0.20),
                "top": top + int(height * 0.45),
                "width": int(width * 0.78),
                "height": int(height * 0.50),
            }

        elif region == "browser":
            crop = {
                "left": left + int(width * 0.08),
                "top": top + int(height * 0.08),
                "width": int(width * 0.88),
                "height": int(height * 0.82),
            }

        elif region == "code":
            crop = {
                "left": left + int(width * 0.05),
                "top": top + int(height * 0.07),
                "width": int(width * 0.90),
                "height": int(height * 0.86),
            }

        elif region == "error":
            crop = {
                "left": left + int(width * 0.10),
                "top": top + int(height * 0.35),
                "width": int(width * 0.85),
                "height": int(height * 0.55),
            }

        else:
            crop = monitor

        screenshot = sct.grab(crop)

        img = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        img.save(SCREENSHOT_FILE)

        return SCREENSHOT_FILE


# ==========================
# IMAGE PREPROCESSING
# ==========================
def preprocess_image(image_path, mode="standard"):
    update_hud(
        status="PROCESSING",
        command="Preprocessing screenshot",
        result="Improving OCR quality...",
        voice="0.2"
    )

    img = cv2.imread(image_path)

    if img is None:
        return image_path

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

    if mode == "code":
        scale = 3.0
        threshold_type = cv2.THRESH_BINARY + cv2.THRESH_OTSU
    elif mode == "terminal":
        scale = 2.6
        threshold_type = cv2.THRESH_BINARY + cv2.THRESH_OTSU
    else:
        scale = 2.5
        threshold_type = cv2.THRESH_BINARY + cv2.THRESH_OTSU

    gray = cv2.resize(
        gray,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC
    )

    gray = cv2.bilateralFilter(
        gray,
        9,
        75,
        75
    )

    thresh = cv2.threshold(
        gray,
        0,
        255,
        threshold_type
    )[1]

    cv2.imwrite(
        PROCESSED_FILE,
        thresh
    )

    return PROCESSED_FILE


# ==========================
# OCR
# ==========================
def ocr_image(image_path, mode="general"):
    update_hud(
        status="PROCESSING",
        command="Reading screen text",
        result="Running OCR...",
        voice="0.4"
    )

    try:
        if mode in {"code", "terminal", "error"}:
            config = "--oem 3 --psm 6"
        else:
            config = "--oem 3 --psm 11"

        text = pytesseract.image_to_string(
            Image.open(image_path),
            config=config
        )

    except Exception as e:
        update_hud(
            status="ERROR",
            command="OCR failed",
            result=short_text(e),
            voice="0.0"
        )
        return f"OCR error: {e}"

    if not text.strip():
        update_hud(
            status="ERROR",
            command="OCR completed",
            result="No readable text found.",
            voice="0.0"
        )
        return "No readable text found on screen."

    update_hud(
        status="SUCCESS",
        command="OCR completed",
        result=short_text(text),
        voice="0.0"
    )

    return text.strip()


# ==========================
# READ SCREEN
# ==========================
def read_screen(region="full"):
    image_path = capture_screen(region)

    preprocess_mode = region if region in {"code", "terminal", "error"} else "standard"

    image_path = preprocess_image(
        image_path,
        mode=preprocess_mode
    )

    return ocr_image(
        image_path,
        mode=region
    )


def read_screen_center():
    return read_screen("center")


def read_terminal():
    return read_screen("terminal")


def read_browser():
    return read_screen("browser")


def read_code_on_screen():
    return read_screen("code")


def read_error_on_screen():
    return read_screen("error")


# ==========================
# SCREENSHOTS
# ==========================
def take_screenshot():
    image_path = capture_screen()

    update_hud(
        status="SUCCESS",
        command="Screenshot captured",
        result=image_path,
        voice="0.0"
    )

    return f"Screenshot captured: {image_path}"


def save_screenshot():
    image_path = capture_screen()

    screenshots_dir = "screenshots"

    os.makedirs(
        screenshots_dir,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    destination = os.path.join(
        screenshots_dir,
        f"screenshot_{timestamp}.png"
    )

    shutil.copy(
        image_path,
        destination
    )

    update_hud(
        status="SUCCESS",
        command="Screenshot saved",
        result=destination,
        voice="0.0"
    )

    return f"Screenshot saved: {destination}"


def describe_screenshot():
    text = read_screen()

    if (
        text.startswith("OCR error")
        or text.startswith("No readable")
    ):
        return text

    prompt = f"""
You are JARVIS.

Describe this screenshot using ONLY the OCR text.

OCR TEXT:
{text}

Return:
1. Main content
2. Visible applications if obvious from text
3. Important information
4. Recommended next action

Keep it concise.
"""

    update_hud(
        status="PROCESSING",
        command="Describing screenshot",
        result="Asking local AI...",
        voice="0.4"
    )

    result = ask_llm(prompt)

    update_hud(
        status="SUCCESS",
        command="Screenshot described",
        result=short_text(result),
        voice="0.0"
    )

    return result


# ==========================
# ANALYZE SCREEN
# ==========================
def analyze_screen(region="full"):
    text = read_screen(region)

    if text.startswith("OCR error") or text.startswith("No readable"):
        return text

    prompt = f"""
You are JARVIS.

IMPORTANT:
- Use ONLY the OCR text provided.
- Do NOT invent applications.
- Do NOT invent browser tabs.
- Do NOT invent CPU usage.
- Do NOT invent RAM usage.
- Do NOT invent disk usage.
- If information is missing say: Not visible.
- If OCR quality is poor say: OCR quality is low.

SCREEN REGION:
{region}

OCR TEXT:
{text}

Return:
1. Visible content
2. Errors found
3. Suggested next action
4. Confidence level: High / Medium / Low

Keep the answer short and practical.
"""

    update_hud(
        status="PROCESSING",
        command=f"Analyzing screen: {region}",
        result="Asking local AI...",
        voice="0.5"
    )

    result = ask_llm(prompt)

    update_hud(
        status="SUCCESS",
        command=f"Screen analyzed: {region}",
        result=short_text(result),
        voice="0.0"
    )

    return result


def analyze_screen_center():
    return analyze_screen("center")


def analyze_terminal():
    return analyze_screen("terminal")


def analyze_browser():
    return analyze_screen("browser")


def analyze_code_on_screen():
    text = read_screen("code")

    if text.startswith("OCR error") or text.startswith("No readable"):
        return text

    prompt = f"""
You are JARVIS, a strict code reviewer.

Use ONLY the OCR text below.
It may contain OCR mistakes, so mention uncertainty if needed.

CODE / EDITOR OCR TEXT:
{text}

Return:
1. What code appears to be visible
2. Possible bugs or risky logic
3. Security concerns
4. Concrete next action
5. Confidence level: High / Medium / Low

Keep it practical and concise.
"""

    update_hud(
        status="PROCESSING",
        command="Reviewing code on screen",
        result="Asking local AI...",
        voice="0.5"
    )

    result = ask_llm(prompt)

    update_hud(
        status="SUCCESS",
        command="Code screen reviewed",
        result=short_text(result),
        voice="0.0"
    )

    return result


def explain_error_on_screen():
    text = read_screen("error")

    if text.startswith("OCR error") or text.startswith("No readable"):
        return text

    prompt = f"""
You are JARVIS, a debugging assistant.

Use ONLY the OCR text below.
Focus on visible error messages, stack traces, terminal output, or warnings.

ERROR / TERMINAL OCR TEXT:
{text}

Return:
1. Most likely error
2. Root cause based only on visible text
3. Exact fix steps
4. Command to try next, if visible
5. Confidence level: High / Medium / Low

Be concise and practical.
"""

    update_hud(
        status="PROCESSING",
        command="Explaining screen error",
        result="Asking local AI...",
        voice="0.5"
    )

    result = ask_llm(prompt)

    update_hud(
        status="SUCCESS",
        command="Error explained",
        result=short_text(result),
        voice="0.0"
    )

    return result


def review_code_on_screen():
    return analyze_code_on_screen()


def find_bugs_on_screen():
    return analyze_code_on_screen()


def what_error_is_on_screen():
    return explain_error_on_screen()


# ==========================
# SCREEN MEMORY
# ==========================
def remember_current_screenshot():
    image_path = capture_screen()

    processed_path = preprocess_image(
        image_path
    )

    text = ocr_image(
        processed_path
    )

    if (
        text.startswith("OCR error")
        or text.startswith("No readable")
    ):
        return text

    prompt = f"""
Summarize this screenshot in one short sentence.

TEXT:
{text}
"""

    summary = ask_llm(prompt)

    remember_screenshot(
        image_path,
        text,
        summary
    )

    update_hud(
        status="SUCCESS",
        command="Screenshot remembered",
        result=short_text(summary),
        voice="0.0"
    )

    return "Screenshot saved to memory."


def what_was_on_my_screen():
    return get_last_screenshot()


def search_screenshot_memory(keyword):
    return search_screenshots(keyword)
