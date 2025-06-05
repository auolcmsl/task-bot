import asyncio
import logging
import os
import tempfile
import subprocess
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, Voice
import speech_recognition as sr
from pydub import AudioSegment
import ffmpeg
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import config
from models import Base, User, Task
from nlp_utils import extract_task_info, extract_user_mention

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# Database setup
engine = create_engine(config.DATABASE_URL)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def convert_ogg_to_wav(ogg_path: str, wav_path: str) -> bool:
    """Convert OGG to WAV using ffmpeg with timeout"""
    try:
        # Use subprocess instead of ffmpeg-python for better control
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', ogg_path, wav_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        try:
            # Wait for process with timeout
            await asyncio.wait_for(process.communicate(), timeout=10.0)
            return process.returncode == 0
        except asyncio.TimeoutError:
            process.kill()
            logger.error("FFmpeg conversion timed out")
            return False
    except Exception as e:
        logger.error(f"Error in convert_ogg_to_wav: {e}")
        return False

async def convert_voice_to_text(voice: Voice) -> str:
    """Convert voice message to text using speech recognition"""
    try:
        logger.info("Starting voice message processing")
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as ogg_file, \
             tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
            
            logger.info("Downloading voice file")
            # Download voice file
            voice_file = await bot.download(voice)
            ogg_file.write(voice_file.read())
            ogg_file.flush()
            logger.info(f"Voice file saved to {ogg_file.name}")
            
            try:
                logger.info("Converting OGG to WAV")
                # Convert ogg to wav using ffmpeg with timeout
                if not await convert_ogg_to_wav(ogg_file.name, wav_file.name):
                    logger.error("Failed to convert OGG to WAV")
                    return None
                
                logger.info(f"WAV file saved to {wav_file.name}")
                
                # Recognize speech
                logger.info("Starting speech recognition")
                recognizer = sr.Recognizer()
                with sr.AudioFile(wav_file.name) as source:
                    logger.info("Reading audio file")
                    audio_data = recognizer.record(source)
                    logger.info("Sending to Google Speech Recognition")
                    try:
                        text = recognizer.recognize_google(audio_data, language='ru-RU')
                        logger.info(f"Successfully recognized text: {text}")
                        return text
                    except sr.UnknownValueError:
                        logger.error("Speech recognition could not understand audio")
                        return None
                    except sr.RequestError as e:
                        logger.error(f"Could not request results from speech recognition service: {e}")
                        return None
            finally:
                # Clean up temporary files
                logger.info("Cleaning up temporary files")
                try:
                    os.unlink(ogg_file.name)
                    os.unlink(wav_file.name)
                except Exception as e:
                    logger.error(f"Error cleaning up files: {e}")
    except Exception as e:
        logger.error(f"Error in convert_voice_to_text: {e}", exc_info=True)
        return None

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Handle the /start command"""
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username
        )
        db.add(user)
        db.commit()
    
    await message.answer(
        "👋 Привет! Я бот для управления задачами.\n\n"
        "Вы можете создавать задачи, используя естественный язык.\n"
        "Например: 'Создать задачу: Подготовить отчет к завтрашнему дню. Важно!'\n\n"
        "Также вы можете создавать задачи голосовыми сообщениями! 🎤",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Handle the /help command"""
    help_text = """
🤖 Доступные команды:

/mytasks - Показать задачи, назначенные мне
/created_tasks - Показать задачи, которые я создал
/assign <ID задачи> @username - Назначить задачу пользователю
/delete <ID задачи> - Удалить задачу
/edit <ID задачи> <новое название> - Изменить название задачи
/help - Показать это сообщение

Примеры создания задач:
- "Создать задачу: Подготовить отчет к завтрашнему дню"
- "Новая задача: Связаться с клиентом @username до пятницы"
- "Задача: Обновить документацию (низкий приоритет)"

🎤 Вы также можете создавать задачи голосовыми сообщениями!
    """
    await message.answer(help_text, reply_markup=types.ReplyKeyboardRemove())

@dp.message(Command("created_tasks"))
async def show_created_tasks(message: Message):
    """Show tasks created by the user"""
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        await message.answer("Вы еще не создали ни одной задачи.", reply_markup=types.ReplyKeyboardRemove())
        return
    
    tasks = user.created_tasks
    
    if not tasks:
        await message.answer("У вас нет созданных задач.", reply_markup=types.ReplyKeyboardRemove())
        return
    
    response = "📋 Задачи, созданные вами:\n\n"
    for task in tasks:
        status_emoji = "✅" if task.is_completed else "⏳"
        response += f"{status_emoji} #{task.id} {task.title}\n"
        if task.description:
            response += f"   📝 {task.description}\n"
        if task.due_date:
            response += f"   ⏰ Срок: {task.due_date.strftime('%d.%m.%Y')}\n"
        response += f"   🎯 Приоритет: {task.priority}\n"
        if task.assignee:
            response += f"   👤 Исполнитель: @{task.assignee.username}\n"
        response += "\n"
    
    await message.answer(response, reply_markup=types.ReplyKeyboardRemove())

@dp.message(lambda message: message.text and any(phrase in message.text.lower() for phrase in ["создать задачу", "новая задача", "задача:"]))
async def create_task(message: Message):
    """Handle natural language task creation"""
    await process_task_creation(message, message.text)

@dp.message(lambda message: message.voice is not None)
async def handle_voice(message: Message):
    """Handle voice messages"""
    try:
        logger.info("Received voice message")
        # Send processing message
        processing_msg = await message.answer("🎤 Обрабатываю голосовое сообщение...")
        
        # Convert voice to text
        logger.info("Converting voice to text")
        text = await convert_voice_to_text(message.voice)
        
        if not text:
            logger.error("Failed to recognize voice message")
            await processing_msg.edit_text("❌ Не удалось распознать голосовое сообщение. Пожалуйста, попробуйте еще раз или используйте текстовый формат.")
            return
        
        # Edit processing message to show recognized text
        logger.info(f"Recognized text: {text}")
        await processing_msg.edit_text(f"🎤 Распознано: {text}\n\nСоздаю задачу...")
        
        # Process the task
        await process_task_creation(message, text)
    except Exception as e:
        logger.error(f"Error in handle_voice: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обработке голосового сообщения. Пожалуйста, попробуйте еще раз или используйте текстовый формат.")

async def process_task_creation(message: Message, text: str):
    """Process task creation from text"""
    try:
        logger.info(f"Processing task creation with text: {text}")
        db = next(get_db())
        
        # Get or create user
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            user = User(telegram_id=message.from_user.id, username=message.from_user.username)
            db.add(user)
            db.commit()
        
        # Extract task information
        title, description, due_date, priority = extract_task_info(text)
        assignee_username = extract_user_mention(text)
        
        # Create task
        task = Task(
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
            creator_id=user.id
        )
        
        if assignee_username:
            assignee = db.query(User).filter(User.username == assignee_username).first()
            if assignee:
                task.assignee_id = assignee.id
        
        db.add(task)
        db.commit()
        
        # Prepare response message
        response = f"✅ Задача создана:\n\n"
        response += f"📌 {task.title}\n"
        if task.description:
            response += f"📝 {task.description}\n"
        if task.due_date:
            response += f"⏰ Срок: {task.due_date.strftime('%d.%m.%Y')}\n"
        response += f"🎯 Приоритет: {task.priority}\n"
        
        await message.answer(response)
    except Exception as e:
        logger.error(f"Error in process_task_creation: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при создании задачи. Пожалуйста, попробуйте еще раз.")

@dp.message(Command("mytasks"))
async def show_my_tasks(message: Message):
    """Show tasks assigned to the user"""
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        await message.answer("Вы еще не создали ни одной задачи.", reply_markup=types.ReplyKeyboardRemove())
        return
    
    # Get tasks where user is assignee
    tasks = db.query(Task).filter(Task.assignee_id == user.id).all()
    
    if not tasks:
        await message.answer("У вас нет назначенных задач.", reply_markup=types.ReplyKeyboardRemove())
        return
    
    response = "📋 Ваши задачи:\n\n"
    for task in tasks:
        status_emoji = "✅" if task.is_completed else "⏳"
        response += f"{status_emoji} #{task.id} {task.title}\n"
        if task.description:
            response += f"   📝 {task.description}\n"
        if task.due_date:
            response += f"   ⏰ Срок: {task.due_date.strftime('%d.%m.%Y')}\n"
        response += f"   🎯 Приоритет: {task.priority}\n"
        response += f"   👤 Создатель: @{task.creator.username}\n\n"
    
    await message.answer(response, reply_markup=types.ReplyKeyboardRemove())

@dp.message(Command("assign"))
async def assign_task(message: Message):
    """Assign task to a user"""
    try:
        # Parse command arguments
        args = message.text.split()
        if len(args) != 3:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Используйте: /assign <ID задачи> @username\n"
                "Например: /assign 1 @ivan",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

        task_id = args[1]
        assignee_username = args[2].lstrip('@')

        db = next(get_db())
        
        # Get current user
        current_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not current_user:
            await message.answer("❌ Пользователь не найден в базе данных.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Get task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await message.answer("❌ Задача не найдена.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Check if user is the creator of the task
        if task.creator_id != current_user.id:
            await message.answer(
                "❌ Вы можете назначать только те задачи, которые создали сами.\n"
                f"ID создателя задачи: {task.creator_id}\n"
                f"Ваш ID: {current_user.id}",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

        # Get assignee
        assignee = db.query(User).filter(User.username == assignee_username).first()
        if not assignee:
            await message.answer(f"❌ Пользователь @{assignee_username} не найден.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Assign task
        task.assignee_id = assignee.id
        db.commit()

        # Prepare response
        response = f"✅ Задача назначена:\n\n"
        response += f"📌 {task.title}\n"
        if task.description:
            response += f"📝 {task.description}\n"
        if task.due_date:
            response += f"⏰ Срок: {task.due_date.strftime('%d.%m.%Y')}\n"
        response += f"🎯 Приоритет: {task.priority}\n"
        response += f"👤 Исполнитель: @{assignee.username}"

        await message.answer(response, reply_markup=types.ReplyKeyboardRemove())

        # Notify assignee
        try:
            await bot.send_message(
                assignee.telegram_id,
                f"📬 Вам назначена новая задача:\n\n"
                f"📌 {task.title}\n"
                f"👤 От: @{message.from_user.username}",
                reply_markup=types.ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Failed to notify assignee: {e}")

    except Exception as e:
        logger.error(f"Error in assign_task: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при назначении задачи. Пожалуйста, попробуйте еще раз.", reply_markup=types.ReplyKeyboardRemove())

@dp.message(Command("delete"))
async def delete_task(message: Message):
    """Delete a task"""
    try:
        # Parse command arguments
        args = message.text.split(maxsplit=1)
        if len(args) != 2:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Используйте: /delete <ID задачи>\n"
                "Например: /delete 1",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

        task_id = args[1]
        db = next(get_db())
        
        # Get current user
        current_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not current_user:
            await message.answer("❌ Пользователь не найден в базе данных.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Get task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await message.answer("❌ Задача не найдена.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Check if user is the creator of the task
        if task.creator_id != current_user.id:
            await message.answer("❌ Вы можете удалять только те задачи, которые создали сами.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Delete task
        db.delete(task)
        db.commit()

        await message.answer(f"✅ Задача #{task.id} успешно удалена.", reply_markup=types.ReplyKeyboardRemove())

    except Exception as e:
        logger.error(f"Error in delete_task: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при удалении задачи. Пожалуйста, попробуйте еще раз.", reply_markup=types.ReplyKeyboardRemove())

@dp.message(Command("edit"))
async def edit_task(message: Message):
    """Edit a task"""
    try:
        # Parse command arguments
        args = message.text.split(maxsplit=2)
        if len(args) != 3:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Используйте: /edit <ID задачи> <новое название>\n"
                "Например: /edit 1 Новое название задачи",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return

        task_id = args[1]
        new_title = args[2]
        
        db = next(get_db())
        
        # Get current user
        current_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not current_user:
            await message.answer("❌ Пользователь не найден в базе данных.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Get task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await message.answer("❌ Задача не найдена.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Check if user is the creator of the task
        if task.creator_id != current_user.id:
            await message.answer("❌ Вы можете редактировать только те задачи, которые создали сами.", reply_markup=types.ReplyKeyboardRemove())
            return

        # Update task
        old_title = task.title
        task.title = new_title
        db.commit()

        # Prepare response
        response = f"✅ Задача обновлена:\n\n"
        response += f"📌 Старое название: {old_title}\n"
        response += f"📌 Новое название: {task.title}\n"
        if task.description:
            response += f"📝 {task.description}\n"
        if task.due_date:
            response += f"⏰ Срок: {task.due_date.strftime('%d.%m.%Y')}\n"
        response += f"🎯 Приоритет: {task.priority}\n"
        if task.assignee:
            response += f"👤 Исполнитель: @{task.assignee.username}"

        await message.answer(response, reply_markup=types.ReplyKeyboardRemove())

        # Notify assignee if exists
        if task.assignee:
            try:
                await bot.send_message(
                    task.assignee.telegram_id,
                    f"📝 Задача обновлена:\n\n"
                    f"📌 {task.title}\n"
                    f"👤 От: @{message.from_user.username}",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            except Exception as e:
                logger.error(f"Failed to notify assignee: {e}")

    except Exception as e:
        logger.error(f"Error in edit_task: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при редактировании задачи. Пожалуйста, попробуйте еще раз.", reply_markup=types.ReplyKeyboardRemove())

async def main():
    # Set up commands menu
    commands = [
        types.BotCommand(command="mytasks", description="Показать задачи, назначенные мне"),
        types.BotCommand(command="created_tasks", description="Показать задачи, которые я создал"),
        types.BotCommand(command="assign", description="Назначить задачу пользователю"),
        types.BotCommand(command="delete", description="Удалить задачу"),
        types.BotCommand(command="edit", description="Изменить название задачи"),
        types.BotCommand(command="help", description="Показать справку")
    ]
    await bot.set_my_commands(commands)
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 