import torch
import os
import uuid
import coloredlogs
import functools
import asyncio
from logging import info, error, warn
from diffusers import StableDiffusionPipeline, ModelMixin
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from concurrent.futures import ProcessPoolExecutor

coloredlogs.install(level='INFO')

pool_executor = ProcessPoolExecutor(1)


def run_in_executor(f):
    @functools.wraps(f)
    def inner(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(None, lambda: f(*args, **kwargs))

    return inner


class NoCheck(ModelMixin):
    """Can be used in place of safety checker. Use responsibly and at your own risk."""
    def __init__(self):
        super().__init__()
        self.register_parameter(name='asdf',
                                param=torch.nn.Parameter(torch.randn(3)))

    def forward(self, images=None, **kwargs):
        warn('Skipping NSFW check')
        return images, [False]


class DiffusionThing:
    def __init__(self):
        info('Initializing model')
        pipe = StableDiffusionPipeline.from_pretrained(
            "CompVis/stable-diffusion-v1-4", use_auth_token=True)
        pipe.safety_checker = NoCheck()
        pipe.enable_attention_slicing()
        device = 'cuda'
        if torch.backends.mps.is_available():
            device = 'mps'
        info(f'Moving model to {device}')
        self.pipe = pipe.to(device)

    @run_in_executor
    def run(self, prompt: str) -> str:
        info(f"Generating {prompt}")
        image = self.pipe(prompt).images[0]
        id = uuid.uuid1()
        fname = f"images/{id}.png"
        info(f"Saving to {fname}")
        image.save(fname)
        return fname


diffusion = DiffusionThing()


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.replace("/gen", "").strip()
    try:
        fname = await diffusion.run(prompt)
        with open(fname, 'rb') as photo:
            await context.bot.send_photo(chat_id=update.effective_chat.id,
                                         photo=photo,
                                         caption=prompt)
    except Exception as e:
        error(e)
        await update.message.reply_text(f"Exception: {e}")
    # os.remove(fname)


if __name__ == '__main__':
    token = os.getenv('TG_TOKEN')
    application = ApplicationBuilder().token(token).build()
    start_handler = CommandHandler('gen', generate)
    application.add_handler(start_handler)
    application.run_polling()
