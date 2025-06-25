import logging
import os
import requests
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Token from Environment Variable ---
# IMPORTANT: Store your bot token in Render environment variables (KEY: BOT_TOKEN)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set.")
    # Fallback for local testing, but should be set in production
    # DO NOT hardcode your token in production code!
    BOT_TOKEN = "YOUR_FALLBACK_BOT_TOKEN_FOR_LOCAL_TESTING" # Replace if testing locally without env var

# --- Terabox API Endpoints ---
# These APIs are external and their reliability/availability may vary.
API_WORKER_1_BASE = 'https://tera.iqbalalam8675.workers.dev/'
API_WORKER_2_BASE = 'https://teraboxapi.thory.workers.dev/api'
API_WORKER_3_BASE = 'https://terabox-pro-api.vercel.app/api' # Correctly parsed now

# --- Helper Function to Escape Markdown V2 Special Characters ---
def escape_markdown_v2(text: str) -> str:
    """
    Helper function to escape all MarkdownV2 special characters.
    This is necessary for any text that is NOT part of a Markdown entity (e.g., link URL, bold text content).
    """
    # List of all special characters that need to be escaped in MarkdownV2
    # This list is from Telegram Bot API documentation.
    # The order of replacement matters: escape backslash itself first.
    special_chars = [
        '\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    ]
    
    # Escape characters by replacing them with a backslash prefix
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    return text

# --- Helper Function to Extract Terabox Link ---
def extract_terabox_link(text):
    """
    Extracts a Terabox share link from a given text.
    Handles various Terabox domains.
    """
    # Regex to match common Terabox domains and share link patterns
    match = re.search(r'(https?://(?:www\.)?terabox(?:app)?\.com/s/[a-zA-Z0-9_-]+|https?://(?:www\.)?1024terabox\.com/s/[a-zA-Z0-9_-]+)', text)
    if match:
        return match.group(0)
    return None

# --- Terabox API Fetch Functions ---
async def fetch_from_api1(terabox_url):
    """Fetches video data from API Worker 1."""
    try:
        api_url = f"{API_WORKER_1_BASE}?url={terabox_url}"
        logger.info(f"Attempting to fetch from API 1: {api_url}")
        response = requests.get(api_url, timeout=15) # Increased timeout
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()
        logger.info(f"API 1 response: {data}")

        if data.get('status') == 'success' and data.get('list'):
            for item in data['list']:
                if item.get('type') == 'video' and item.get('playUrl'):
                    return {
                        'title': item.get('name', 'Video'),
                        'url': item['playUrl'],
                        'size': item.get('size'),
                        'thumbnail': item.get('image')
                    }
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API 1 Request error: {e}")
        return None
    except ValueError as e:
        logger.error(f"API 1 JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"API 1 unexpected error: {e}")
        return None

async def fetch_from_api2(terabox_url):
    """Fetches video data from API Worker 2."""
    try:
        api_url = f"{API_WORKER_2_BASE}?key=free&url={terabox_url}"
        logger.info(f"Attempting to fetch from API 2: {api_url}")
        response = requests.get(api_url, timeout=15) # Increased timeout
        response.raise_for_status()
        data = response.json()
        logger.info(f"API 2 response: {data}")

        if data.get('status') == 'success' and data.get('download_link'):
            return {
                'title': data.get('file_name', 'Video'),
                'url': data['download_link'],
                'size': data.get('file_size'),
                'thumbnail': data.get('thumbnail')
            }
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API 2 Request error: {e}")
        return None
    except ValueError as e:
        logger.error(f"API 2 JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"API 2 unexpected error: {e}")
        return None

async def fetch_from_api3(terabox_url):
    """Fetches video data from API Worker 3."""
    try:
        api_url = f"{API_WORKER_3_BASE}?link={terabox_url}"
        logger.info(f"Attempting to fetch from API 3: {api_url}")
        response = requests.get(api_url, timeout=15) # Increased timeout
        response.raise_for_status()
        data = response.json()
        logger.info(f"API 3 response: {data}")

        if data.get('status') == '✅ Success' and data.get('📋 Extracted Info') and len(data['📋 Extracted Info']) > 0:
            extracted_info = data['📋 Extracted Info'][0]
            if extracted_info.get('🔗 Direct Download Link'):
                thumbnail_url = None
                if extracted_info.get('🖼️ Thumbnails'):
                    # Prioritize larger thumbnails
                    thumbnails = extracted_info['🖼️ Thumbnails']
                    thumbnail_url = thumbnails.get("850x580") or thumbnails.get("360x270") or thumbnails.get("140x90") or thumbnails.get("60x60")

                return {
                    'title': extracted_info.get('📄 Title', 'Video'),
                    'url': extracted_info['🔗 Direct Download Link'],
                    'size': extracted_info.get('📦 Size'), # This API gives size as a formatted string
                    'thumbnail': thumbnail_url
                }
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API 3 Request error: {e}")
        return None
    except ValueError as e:
        logger.error(f"API 3 JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"API 3 unexpected error: {e}")
        return None

# --- Bot Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the command /start is issued."""
    await update.message.reply_text(
        "Hi! Send me a Terabox share link, and I'll try to get the direct video or download link for you.\n"
        "Example: `https://teraboxapp.com/s/1h97DwtT0zc0uDzfNNWbCsA`"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the command /help is issued."""
    await update.message.reply_text(
        "Send me a Terabox share link. I will process it and provide a downloadable video link or file if available.\n\n"
        "**Important Note:** Some Terabox links (especially for free accounts) might only provide previews or expire quickly. I'll do my best to get the full video, but it's not guaranteed by the external APIs.\n\n"
        "Example: `https://1024terabox.com/s/1lqQc8B3zvkwh5cqByDatog`"
    )

async def handle_terabox_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles incoming messages, attempts to extract a Terabox link,
    fetches video data, and sends it back to the user.
    """
    user_message = update.message.text
    terabox_link = extract_terabox_link(user_message)

    if not terabox_link:
        await update.message.reply_text(
            "That doesn't look like a valid Terabox share link. Please send a link like:\n"
            "`https://teraboxapp.com/s/some_share_id` or `https://1024terabox.com/s/some_share_id`"
        )
        return

    await update.message.reply_text(f"Received your link: `{terabox_link}`\n\nProcessing... This might take a moment (up to 30 seconds due to API calls).", parse_mode='Markdown')

    video_info = None

    # Try APIs in order (API 3, then API 1, then API 2)
    # Using a list of (fetch_function, api_name_for_logging) tuples
    api_fetchers = [
        (fetch_from_api3, "API 3"),
        (fetch_from_api1, "API 1"),
        (fetch_from_api2, "API 2")
    ]

    for fetch_func, api_name in api_fetchers:
        logger.info(f"Trying {api_name}...")
        video_info = await fetch_func(terabox_link)
        # Add a check for common "download down" messages from APIs
        if video_info and video_info.get('url') and "download feature is currently down" not in video_info['url'].lower():
            logger.info(f"Successfully got info from {api_name}")
            break
        else:
            logger.warning(f"{api_name} failed or returned no useful info.")

    if video_info and video_info.get('url'):
        try:
            video_url = video_info['url']
            
            # ESCAPE TITLE AND SIZE_STR FOR MARKDOWN V2 using the improved function
            escaped_title = escape_markdown_v2(video_info.get('title', 'Terabox Video'))
            escaped_size_str = escape_markdown_v2(video_info.get('size', 'Unknown size'))
            
            thumbnail_url = video_info.get('thumbnail')

            # Ensure the video_url is a valid HTTP/HTTPS URL
            if not video_url.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid video URL received: {video_url}")

            # Construct caption with escaped text parts and an explicitly escaped link text for the button
            # Note: The URL itself in the link part [text](url) does NOT need escaping.
            caption = (
                f"🎬 *{escaped_title}*\n"
                f"📦 Size: {escaped_size_str}\n\n"
                # The text "Direct Download Link (Click here)" itself needs its parentheses escaped
                f"[⬇️ Direct Download Link \\(Click here\\)]({video_url})" 
            )
            logger.info(f"Final caption to send: {caption}") # Log the final caption
            
            # Telegram's send_video supports URLs up to 2GB directly.
            # It will fetch the video from the provided URL.
            await update.message.reply_video(
                video=video_url,
                caption=caption,
                parse_mode='MarkdownV2', # Explicitly use MarkdownV2
                thumbnail=thumbnail_url, # Pass thumbnail URL directly
                read_timeout=60, # Increased timeout for large files
                write_timeout=60,
                connect_timeout=60
            )

            await update.message.reply_text(
                "If the video doesn't play directly or download, try clicking the 'Direct Download Link' in the message above or open it in your browser/download manager.\n\n"
                "❗ **Important Note:** Full-length streaming via direct links may be limited by Terabox's service policies on free accounts. For complete videos, offline playback or usage of the official Terabox app/website is generally more reliable."
            )

        except Exception as e:
            logger.error(f"Error sending video to Telegram: {e}", exc_info=True) # Log full traceback
            error_message_for_user = "an unknown error"
            if "Failed to get http url content" in str(e):
                error_message_for_user = "Telegram couldn't access the video content from the provided URL. The link might be expired or restricted."
            elif "Can't parse entities" in str(e): # This shouldn't happen with latest escaping, but for robustness
                error_message_for_user = "a formatting error in the message. Trying to fix it now."

            await update.message.reply_text(
                f"Sorry, I encountered an error while trying to send the video: {error_message_for_user}\n\n"
                "Please try clicking the direct link below."
            )
            # As a fallback, send just the direct link as text
            if video_info.get('url'):
                await update.message.reply_text(
                    f"Here's the direct link you can try manually downloading:\n\n`{escape_markdown_v2(video_info['url'])}`\n\n" # Escape URL in fallback for safety
                    "Remember, some links may have playback restrictions."
                    , parse_mode='MarkdownV2' # Keep MarkdownV2 for fallback message too
                )
    else:
        await update.message.reply_text(
            "Sorry, I couldn't find a playable video for that Terabox link using any of the available APIs. The link might be invalid, expired, or the content type is not supported."
        )

# --- Flask App for Webhooks ---
app = Flask(__name__)
application_instance = None # Global variable to hold the PTB Application instance

@app.route('/', methods=['GET'])
def home():
    return "Terabox Telegram Bot is running!"

@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    global application_instance
    if application_instance is None:
        logger.error("Telegram Application is not initialized.")
        return "Internal server error: Bot not ready", 500

    # Ensure the request body is valid JSON
    if not request.is_json:
        logger.warning("Webhook received non-JSON request.")
        return "Bad Request: Content-Type must be application/json", 400

    update_data = request.get_json(force=True)
    if not update_data:
        logger.warning("Webhook received empty JSON or failed to parse.")
        return "Bad Request: Empty or invalid JSON payload", 400

    try:
        update = Update.de_json(update_data, application_instance.bot)
    except Exception as e:
        logger.error(f"Failed to deserialize Update object: {e}", exc_info=True)
        return f"Internal Server Error: Failed to parse Telegram update. Error: {e}", 500

    # Process the update using the PTB dispatcher
    # For webhook, process_update runs synchronously from the Flask route.
    # It requires the update object directly.
    await application_instance.process_update(update)
    
    return jsonify({"status": "ok"})

def main() -> None:
    """Sets up and runs the bot with webhooks."""
    global application_instance
    
    application_instance = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application_instance.add_handler(CommandHandler("start", start))
    application_instance.add_handler(CommandHandler("help", help_command))

    # Add message handler for all text messages
    application_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_terabox_link))

    # Set up webhook
    # Render provides the PORT as an.environment variable
    port = int(os.environ.get("PORT", "8080")) # Default to 8080 if not set
    # WEBHOOK_URL should be set in Render environment variables
    webhook_base_url = os.environ.get("WEBHOOK_URL") 

    if not webhook_base_url:
        logger.error("WEBHOOK_URL environment variable not set. Fallback to long-polling.")
        logger.info("Running locally for development (long-polling fallback)...")
        application_instance.run_polling(allowed_updates=Update.ALL_TYPES)
    else:
        # Set the webhook with Telegram
        webhook_full_url = f"{webhook_base_url}/webhook"
        logger.info(f"Setting webhook to {webhook_full_url}")
        
        # Start the webhook server
        application_instance.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook", # This must match the Flask route
            webhook_url=webhook_full_url # The full URL Telegram will call
        )
        logger.info(f"Flask app running on port {port}")
        # The Flask app is implicitly run by application.run_webhook
        # No need for app.run() here if using run_webhook, as PTB handles the server.

if __name__ == "__main__":
    main()

