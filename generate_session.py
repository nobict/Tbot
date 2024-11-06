from pyrogram import Client
import asyncio
from dotenv import load_dotenv
import os
import logging
from pyrogram.errors import (
    PhoneCodeExpired, 
    PhoneCodeInvalid, 
    SessionPasswordNeeded,
    PhoneNumberInvalid
)
import time

# Load environment variables
load_dotenv()

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get API credentials from .env file
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

async def generate_session(user_id=None, phone_number=None, code=None, password=None):
    """Generate a session string for a user"""
    client = None
    try:
        logger.info(f"Starting session generation for user {user_id}")
        
        # Create a new client with unique session name
        session_name = f"session_{user_id}_{int(time.time())}" if user_id else "my_account"
        client = Client(
            session_name,
            api_id=api_id,
            api_hash=api_hash,
            in_memory=True
        )
        
        await client.connect()
        
        # If we're just starting (no code provided)
        if not code:
            if not phone_number:
                phone_number = input("Enter phone number: ")
            sent_code = await client.send_code(phone_number)
            return client, sent_code.phone_code_hash
            
        # If we have a code, try to sign in
        try:
            signed_in = await client.sign_in(
                phone_number=phone_number,
                phone_code_hash=code[1],  # phone_code_hash
                phone_code=code[0]  # verification code
            )
            
        except SessionPasswordNeeded:
            if not password:
                password = input("Enter your 2FA password: ")
            signed_in = await client.check_password(password)
            
        # If we successfully signed in, export the session
        if signed_in:
            string_session = await client.export_session_string()
            
            # Save to .env if user_id is provided
            if user_id:
                env_path = '.env'
                env_var = f"USER_STRING_SESSION_{user_id}"
                
                # Read existing content
                existing_lines = []
                if os.path.exists(env_path):
                    with open(env_path, 'r') as f:
                        existing_lines = f.readlines()
                
                # Remove existing entry if present
                existing_lines = [line for line in existing_lines 
                                if not line.startswith(f"{env_var}=")]
                
                # Add new session string
                existing_lines.append(f"{env_var}={string_session}\n")
                
                # Write back to file
                with open(env_path, 'w') as f:
                    f.writelines(existing_lines)
                
                logger.info(f"Session string saved for user {user_id}")
                
            return string_session
                    
    except Exception as e:
        logger.error(f"Error generating session: {str(e)}")
        raise
        
    finally:
        if client and client.is_connected:
            await client.disconnect()

# Simple command-line interface for testing
if __name__ == "__main__":
    asyncio.run(generate_session())