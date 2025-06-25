import logging
import os
import requests
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, jsonify
import asyncio # Import asyncio for direct webhook setting

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Token from Environment Variable ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set. Please set it for production.")
    # Fallback for local testing, but should NOT be used in production
    BOT_TOKEN = "YOUR_FALLBACK_BOT_TOKEN_FOR_LOCAL_TESTING" 

# --- Terabox API Endpoints ---
API_WORKER_1_BASE = 'https://tera.iqbalalam8675.workers.dev/'
API_WORKER_2_BASE = 'https://teraboxapi.thory.workers.dev/api'
API_WORKER_3_BASE = 'https://terabox-pro-api.vercel.app/api'

# --- Helper Function to Escape Markdown V2 Special Characters ---
def escape_markdown_v2(text: str) -> str:
    """
    Helper function to escape all MarkdownV2 special characters.
    This is necessary for any text that is NOT part of a Markdown entity (e.g., link URL, bold text content).
    """
    special_chars = [
        '\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    ]
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    return text

# --- Helper Function to Extract Terabox Link ---
def extract_terabox_link(text):
    """
    Extracts a Terabox share link from a given text.
    Handles various Terabox domains.
    """
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
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
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
        response = requests.get(api_url, timeout=15)
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
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        data = response.json()
        logger.info(f"API 3 response: {data}")

        if data.get('status') == '✅ Success' and data.get('📋 Extracted Info') and len(data['📋 Extracted Info']) > 0:
            extracted_info = data['📋 Extracted Info'][0]
            if extracted_info.get('🔗 Direct Download Link'):
                thumbnail_url = None
                if extracted_info.get('🖼️ Thumbnails'):
                    thumbnails = extracted_info['🖼️ Thumbnails']
                    thumbnail_url = thumbnails.get("850x580") or thumbnails.get("360x270") or thumbnails.get("140x90") or thumbnails.get("60x60")

                return {
                    'title': extracted_info.get('📄 Title', 'Video'),
                    'url': extracted_info['🔗 Direct Download Link'],
                    'size': extracted_info.get('📦 Size'),
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
    api_fetchers = [
        (fetch_from_api3, "API 3"),
        (fetch_from_api1, "API 1"),
        (fetch_from_api2, "API 2")
    ]

    for fetch_func, api_name in api_fetchers:
        logger.info(f"Trying {api_name}...")
        video_info = await fetch_func(terabox_link)
        if video_info and video_info.get('url') and "download feature is currently down" not in video_info['url'].lower():
            logger.info(f"Successfully got info from {api_name}")
            break
        else:
            logger.warning(f"{api_name} failed or returned no useful info.")

    if video_info and video_info.get('url'):
        try:
            video_url = video_info['url']
            
            escaped_title = escape_markdown_v2(video_info.get('title', 'Terabox Video'))
            escaped_size_str = escape_markdown_v2(video_info.get('size', 'Unknown size'))
            
            thumbnail_url = video_info.get('thumbnail')

            if not video_url.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid video URL received: {video_url}")

            caption = (
                f"🎬 *{escaped_title}*\n"
                f"📦 Size: {escaped_size_str}\n\n"
                f"[⬇️ Direct Download Link \\(Click here\\)]({video_url})" 
            )
            logger.info(f"Final caption to send: {caption}")
            
            await update.message.reply_video(
                video=video_url,
                caption=caption,
                parse_mode='MarkdownV2',
                thumbnail=thumbnail_url,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60
            )

            await update.message.reply_text(
                "If the video doesn't play directly or download, try clicking the 'Direct Download Link' in the message above or open it in your browser/download manager.\n\n"
                "❗ **Important Note:** Full-length streaming via direct links may be limited by Terabox's service policies on free accounts. For complete videos, offline playback or usage of the official Terabox app/website is generally more reliable."
            )

        except Exception as e:
            logger.error(f"Error sending video to Telegram: {e}", exc_info=True)
            error_message_for_user = "an unknown error"
            if "Failed to get http url content" in str(e):
                error_message_for_user = "Telegram couldn't access the video content from the provided URL. The link might be expired or restricted."
            elif "Can't parse entities" in str(e): 
                error_message_for_user = "a formatting error in the message. Trying to fix it now."

            await update.message.reply_text(
                f"Sorry, I encountered an error while trying to send the video: {error_message_for_user}\n\n"
                "Please try clicking the direct link below."
            )
            if video_info.get('url'):
                await update.message.reply_text(
                    f"Here's the direct link you can try manually downloading:\n\n`{escape_markdown_v2(video_info['url'])}`\n\n"
                    "Remember, some links may have playback restrictions."
                    , parse_mode='MarkdownV2' 
                )
    else:
        await update.message.reply_text(
            "Sorry, I couldn't find a playable video for that Terabox link using any of the available APIs. The link might be invalid, expired, or the content type is not supported."
        )

# --- Flask App for Webhooks ---
app = Flask(__name__)
# Initialize application_instance directly when module is loaded
application_instance = Application.builder().token(BOT_TOKEN).build()
# Add handlers to the application_instance
application_instance.add_handler(CommandHandler("start", start))
application_instance.add_handler(CommandHandler("help", help_command))
application_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_terabox_link))
logger.info("Telegram Application initialized and handlers added.")


@app.route('/', methods=['GET'])
def home():
    return "Terabox Telegram Bot is running! Visit /webhook for Telegram updates."

@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    # application_instance is now guaranteed to be initialized
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

    await application_instance.process_update(update)
    
    return jsonify({"status": "ok"})


# This block ensures the webhook is set when the application starts
# This is typically managed by a separate script or a startup hook in production
# For Render, we ensure the webhook is set when gunicorn loads the app.
# The code below will run ONCE when `bot.py` is imported by Gunicorn.
if __name__ == '__main__':
    # This block is primarily for local testing with `python bot.py`
    # In Render, Gunicorn will import `app` directly and this block won't run.
    logger.warning("Running bot.py directly. This is for local testing ONLY. Use Gunicorn for production.")
    
    # For local polling
    # application_instance.run_polling(allowed_updates=Update.ALL_TYPES)
    
    # For local webhook testing (requires ngrok or similar)
    # WEBHOOK_URL must be an accessible URL like ngrok's HTTPS URL + /webhook
    # local_port = int(os.environ.get("PORT", 8080))
    # application_instance.run_webhook(
    #     listen="0.0.0.0",
    #     port=local_port,
    #     url_path="webhook",
    #     webhook_url=f"{os.getenv('WEBHOOK_URL_LOCAL')}/webhook" # Use a local env var for ngrok URL
    # )
    # app.run(host="0.0.0.0", port=local_port)

else:
    # This block runs when Gunicorn imports the 'bot' module
    # We ensure the webhook is set with Telegram when Render brings up the service.
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if WEBHOOK_URL:
        webhook_full_url = f"{WEBHOOK_URL}/webhook"
        # We need to run an async function to set the webhook
        # Gunicorn might not provide an event loop here directly on module load.
        # This is a common pattern for "one-time async setup" in WSGI apps.
        async def _set_webhook_on_startup():
            try:
                current_webhook_info = await application_instance.bot.get_webhook_info()
                if current_webhook_info.url != webhook_full_url:
                    logger.info(f"Setting Telegram webhook to: {webhook_full_url}")
                    await application_instance.bot.set_webhook(url=webhook_full_url)
                else:
                    logger.info(f"Telegram webhook already set to: {webhook_full_url}")
            except Exception as e:
                logger.error(f"Error during webhook setup on startup: {e}", exc_info=True)

        # Ensure the async function runs.
        # This is the tricky part with Gunicorn. It generally expects synchronous code on import.
        # However, for a one-off async call like set_webhook, we can try to run it.
        # A more robust solution for complex async init in Gunicorn would be a custom WSGI entrypoint or deferred init.
        # For simple set_webhook, `asyncio.run` should be fine here if Gunicorn doesn't interfere.
        # However, `asyncio.run` needs to run on the main thread and might block Gunicorn's startup.
        # A better approach is to rely on PTB's internal webhook management when `run_webhook` is called.
        # But we are not calling `run_webhook` in the Gunicorn context, Gunicorn serves Flask.

        # Let's simplify: Gunicorn will run the `app` instance.
        # The bot application instance and handlers are set up.
        # We assume `WEBHOOK_URL` is correctly set in Render environment.
        # The `set_webhook` call should technically only happen once successfully.
        # We rely on the /webhook endpoint to process updates.
        # The `WEBHOOK_URL` needs to be set manually via BotFather or a one-off script
        # OR `python-telegram-bot`'s `run_webhook` must be used to also serve the Flask app.
        # Since we're separating Flask app serving (Gunicorn) from PTB's webhook server:
        # We need to explicitly set the webhook with Telegram somewhere.
        # The `_set_webhook_on_startup` is the right idea, but `asyncio.run` in a WSGI context is risky.

        # Let's re-add a direct call to `set_webhook` outside the if __name__ == '__main__'
        # but within a `try-except` to avoid crashing Gunicorn startup.
        # This will run during module import.

        # This needs a running event loop to `await` anything.
        # Gunicorn might not provide one at this exact point for `await`.
        # The most reliable way for Render is often to ensure the WEBHOOK_URL
        # is set in Render's environment, and then manually call:
        # `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<YOUR_RENDER_WEBHOOK_URL>`
        # in your browser once after deployment.

        # Or, the Application.run_webhook() call could be restructured to use the Flask app.
        # But that complicates the Gunicorn setup.

        # Given the previous `application.run_webhook` approach failed the root URL,
        # the current Flask + Gunicorn setup is better for serving all routes.
        # The missing piece is reliably setting the webhook itself ONCE.

        # Let's try to make the set_webhook part robust during Gunicorn startup
        # by creating a temporary event loop if one isn't running.
        # This is a bit of a hack but often works for simple async startups in sync contexts.

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If a loop is already running (e.g., in a complex Gunicorn setup),
                # schedule the task. This is less common.
                loop.create_task(_set_webhook_on_startup())
            else:
                # If no loop is running (common for Gunicorn worker startup), run it.
                loop.run_until_complete(_set_webhook_on_startup())
        except RuntimeError:
            # If get_event_loop fails, it means no loop is set, or it's closed.
            # Create a new one.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_set_webhook_on_startup())
            loop.close() # Close the temporary loop

    logger.info("Bot logic initialized. Flask app ready for Gunicorn.")


