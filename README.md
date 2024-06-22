# Groove Telegram Chatbot

## Overview
This repository contains the code for the Groove Telegram Chatbot, which is designed to handle user messages and manage chatbot setup via webhook. The bot can be controlled through a website, while CPU-intensive tasks are handled by a separate backend worker.

## Features
1. **Admin Operations**:
   - **Pin/Unpin Messages**: Pin important messages in the chat.
   - **Mute/Unmute Users**: Mute or unmute users to control chat interactions.
   - **Kick Users**: Remove users from the group.
   - **Delete Messages**: Delete unwanted or inappropriate messages.
   - **Register Bot**: Use a token to set up the bot in a group.

2. **User Assistance**:
   - Provides help and support to users through various commands and interactions.

3. **Profanity Filters**:
   - Includes filters to detect and handle profane language, ensuring a safe and respectful environment.

## Technologies Used
- **Language**: Python
- **Module**: `python-telegram-bot`
- **Method**: Webhook for receiving and processing messages
- **Database**: MongoDB for storing user data, settings, and other relevant information

## Usage
Once the bot is running, it will handle incoming messages and execute commands as per the implemented features. The bot can be controlled via the website for admin operations and further customization.

### Admin Commands
- `/pin`: Pin a specific message in the chat.
- `/unpin`: Unpin a specific message.
- `/mute`: Mute a user.
- `/unmute`: Unmute a user.
- `/kick`: Kick a user from the group.
- `/delete`: Delete a specific message.
- `/register <token>`: Set up the bot in a group using a token.

### Profanity Filter
The bot includes a built-in profanity filter that scans messages for inappropriate language and takes appropriate action, such as warning the user or deleting the message.
