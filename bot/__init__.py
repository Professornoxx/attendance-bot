import telegram
from .keyboards import BotKeyboards
from .validation import AttendanceValidationEngine

# Save reference to original reply_text
_original_reply_text = telegram.Message.reply_text

async def patched_reply_text(self, text: str, *args, **kwargs):

    # Enforce that the reply stays within the same topic thread if applicable
    if hasattr(self, 'message_thread_id') and self.message_thread_id is not None:
        kwargs['message_thread_id'] = self.message_thread_id
        
    return await _original_reply_text(self, text, *args, **kwargs)

# Apply patch to Message class
telegram.Message.reply_text = patched_reply_text
