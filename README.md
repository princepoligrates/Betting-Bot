# Betting Bot with Telegram and Google Sheets Integration

## Overview
This project is a **Python-based betting bot** that automates the process of recording betting data from Telegram messages directly into a Google Sheet. It uses the Telegram API to fetch data and the Google Sheets API to store it for accounting purposes.

The bot ensures that bets are tracked accurately, provides a transparent record for accounting, and helps manage betting accounts efficiently.

---

## Features
- **Automated Data Recording**: Fetches betting data from Telegram chats in real time and records it in a Google Sheet.
- **Account Tracking**: Maintains records of which accounts the bets were placed on.
- **Seamless Integration**: Utilizes Telegram’s API and Google Sheets API for smooth data flow.
- **Ease of Use**: Requires minimal manual intervention after initial setup.

---

## Technologies Used
- **Programming Language**: Python
- **APIs**:  
  - [Telegram API](https://core.telegram.org/bots/api)  
  - [Google Sheets API](https://developers.google.com/sheets/api)
- **Libraries**:  
  - `telethon` or `python-telegram-bot` (for interacting with Telegram)  
  - `gspread` or `google-auth` (for working with Google Sheets)

---

## Installation

### Prerequisites
1. Python 3.8+ installed.
2. Telegram Bot API token.
3. Google Cloud project with Sheets API enabled and a service account JSON key.

### Setup Instructions
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/betting-bot.git
   cd betting-bot
