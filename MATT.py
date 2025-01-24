import logging
import os
import re
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import datetime

# Load environment variables
load_dotenv()

# Telegram Bot Token and Google Sheets credentials
TOKEN = os.getenv('TELEGRAM_TOKEN')
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# Validate environment variables
if not all([TOKEN, SERVICE_ACCOUNT_FILE, SPREADSHEET_ID]):
    raise ValueError("Missing required environment variables")

# Get the current month
current_month = datetime.now().strftime("%B")

# Logging configuration
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Google Sheets setup
def get_google_sheets_service():
    credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build('sheets', 'v4', credentials=credentials)

# Initialize Google Sheet
def initialize_google_sheets():
    service = get_google_sheets_service()
    sheet = service.spreadsheets()
    response = sheet.get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = response.get('sheets', [])

    # Check if current month sheet exists
    sheet_id = next((s['properties']['sheetId'] for s in sheets if s['properties']['title'] == current_month), None)
    if sheet_id is None:
        requests = [{"addSheet": {"properties": {"title": current_month}}}]
        response = sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": requests}).execute()
        sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
        logging.info(f"New sheet '{current_month}' created successfully.")

    # Set headers if not already set
    headers = ["Date", "Match", "Amount", "Platform", "Odds", "Correct Odds", "Profit", "Win/Lose", "Outcome $", "Peso", "TXT 2% COMS"]
    range_ = f"{current_month}!A1:K1"
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_).execute()

    if not result.get('values'):
        sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=range_, valueInputOption="RAW", body={'values': [headers]}).execute()
        logging.info("Headers added.")

    # Apply enhanced data validation for "Win/Lose" dropdown
    requests = [
        {
            "setDataValidation": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": 7, "endColumnIndex": 8},
                "rule": {
                    "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "WIN"}, {"userEnteredValue": "LOSE"}, {"userEnteredValue": "DRAW"}]},
                    "showCustomUi": True
                }
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 11},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 1.0, "green": 0.8, "blue": 0.6},
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)"
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": 7, "endColumnIndex": 8}],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": "WIN"}]
                        },
                        "format": {
                            "backgroundColor": {"red": 0.0, "green": 0.6, "blue": 0.0},
                            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True}
                        }
                    }
                },
                "index": 0
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": 7, "endColumnIndex": 8}],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": "LOSE"}]
                        },
                        "format": {
                            "backgroundColor": {"red": 1.0, "green": 0.0, "blue": 0.0},
                            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True}
                        }
                    }
                },
                "index": 1
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": 7, "endColumnIndex": 8}],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": "DRAW"}]
                        },
                        "format": {
                            "backgroundColor": {"red": 0.0, "green": 0.0, "blue": 1.0},
                            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True}
                        }
                    }
                },
                "index": 2
            }
        }
    ]

    sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": requests}).execute()
    return service, sheet, sheet_id

# Pre-compile regular expressions
website_regex = re.compile(r'\b\w+\b', re.IGNORECASE)
match_regex = re.compile(r'([a-zA-Z]+/[a-zA-Z]+)')
time_regex = re.compile(r'\b(1h|2h|ot|ht)\b', re.IGNORECASE)
points_regex = re.compile(r'[uo]\d+|[+-]\d+', re.IGNORECASE)
odds_regex = re.compile(r'@(\d+(\.\d+)?)')
amount_currency_regex = re.compile(r'@\d+(\.\d+)?\s+(\d+[kK]?\s*[A-Za-z]*)', re.IGNORECASE)

def parse_bet_details(bet_details: str):
    details_parts = bet_details.split(" ", 1)
    if len(details_parts) < 2:
        raise ValueError("Invalid bet format.")

    remaining_details = details_parts[1]
    website = website_regex.search(remaining_details).group(0)
    match = match_regex.search(remaining_details).group(0)
    time = time_regex.search(remaining_details)
    points = points_regex.search(remaining_details)
    odds = odds_regex.findall(remaining_details)
    amount_currency_match = amount_currency_regex.search(remaining_details)
    is_total = 'total' in remaining_details.lower()

    if not match or not amount_currency_match or len(odds) < 1:
        raise ValueError("Invalid bet details.")

    time = time.group(0) if time else ""
    points = points.group(0) if points else ""
    bet_odds = odds[0][0]
    correct_odds = odds[1][0] if len(odds) > 1 else "0"
    amount_currency = amount_currency_match.group(2).strip()

    amount_str, currency = amount_currency.split(' ')[0], re.search(r'\b[A-Za-z]{3}\b', amount_currency).group(0) if re.search(r'\b[A-Za-z]{3}\b', amount_currency) else "USD"
    amount = int(amount_str[:-1]) * 1000 if amount_str.endswith('k') else int(amount_str)
    amount = '{:,}'.format(amount)

    if is_total:
        website = 'N/A'
    return website, match, time.upper(), points.upper(), bet_odds, correct_odds, amount, currency.upper(), is_total

async def save_bet_to_google_sheets(website, match, odds, correct_odds, amount, user_input, is_total):
    try:
        service, sheet, sheet_id = initialize_google_sheets()  # Ensure the sheet exists every time

        current_date = datetime.now().strftime("%Y-%m-%d")
        row = [current_date, user_input, amount, website.upper(), odds or "", correct_odds or "", "", "", ""]

        # Fetch all rows from the sheet
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!A:K").execute()
        rows = result.get('values', [])

        # Find last "End of Week" marker
        last_end_of_week_index = -1
        for i, existing_row in enumerate(rows):
            if existing_row and existing_row[0].lower().startswith("end of"):
                last_end_of_week_index = i

        # Check for matches after the last "End of Week" marker
        row_position = len(rows) + 1  # Default position after the last row
        for i in range(last_end_of_week_index + 1, len(rows)):
            if len(rows[i]) > 1 and match in rows[i][1] and is_total:
                row_position = i + 1  # Found a match, set position
                break
            elif len(rows[i]) > 1 and match in rows[i][1]:
                row_position = i + 2

        # If no similar match is found, append after the last "End of Week"
        if row_position <= len(rows):
            sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={
                "requests": [{
                    "insertRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_position - 1,
                            "endRowIndex": row_position
                        },
                        "shiftDimension": "ROWS"
                    }
                }]
            }).execute()

        # Update the Google Sheets with the new bet
        sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!A{row_position}",
                              valueInputOption="RAW", body={"values": [row]}).execute()

        # Add formula to profit and peso column
        profit_formula = f'=IF(AND(H{row_position}="WIN", D{row_position}<>"TEXTODDS"), TEXT(C{row_position} * F{row_position} - C{row_position} * E{row_position}, "#,##0"), "0")'
        peso_formula = f'=TEXT(I{row_position} * 60, "#,##0")'
        outcome_formula = f'=IF(H{row_position}="WIN", C{row_position}*E{row_position}, IF(H{row_position}="LOSE", -C{row_position}, 0))'
        coms_formula = f'=IF(D{row_position}="TEXTODDS", TEXT(C{row_position} * 60 * 0.02, "#,##0.00"), "")'


        sheet.values().update(spreadsheetId=SPREADSHEET_ID,range=f"{current_month}!I{row_position}",
                            valueInputOption="USER_ENTERED", body={"values": [[outcome_formula]]}).execute()
        sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!G{row_position}",
                              valueInputOption="USER_ENTERED", body={"values": [[profit_formula]]}).execute()
        sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!J{row_position}",
                              valueInputOption="USER_ENTERED", body={"values": [[peso_formula]]}).execute()
        sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!K{row_position}",
                              valueInputOption="USER_ENTERED", body={"values": [[coms_formula]]}).execute()


        logging.info(f"Bet saved to row {row_position}.")
    except Exception as e:
        logging.error(f"Error saving bet to Google Sheets: {e}")
        raise
    logging.info(f"Saving bet: {user_input} with amount: {amount}")

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Welcome to the Betting Bot!\n"
        "You can log your bets using the /bet command.\n"
        "For example:\n"
        "/bet <website> <match> <points> <odds> <amount> <currency>"
    )

async def bet(update: Update, context: CallbackContext):
    user_input = " ".join(context.args)
    try:
        website, match, time, points, bet_odds, correct_odds, amount, currency, is_total = parse_bet_details(user_input)
        website = context.args[0] if not is_total else 'N/A'

        await save_bet_to_google_sheets(website, match, bet_odds, correct_odds, amount, user_input, is_total)
        summary = (
            f"Bet saved successfully!\n\n"
            f"----Bet Summary----\n"
            f"Website: {website.upper()}\n"
            f"Match: {match.upper()} {time or ''} {points or ''}\n"
            f"Odds: {bet_odds}\n"
            f"Correct Odds: {correct_odds or 'N/A'}\n"
            f"Amount: {amount} {currency}\n"
        )
        await update.message.reply_text(summary)

    except ValueError as e:
        await update.message.reply_text(f"Error: {e}")
    except Exception:
        await update.message.reply_text("An unexpected error occurred. Please try again later.")

async def end_of_week(update: Update, context: CallbackContext):
    try:
        service, sheet, sheet_id = initialize_google_sheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!A:K").execute()
        rows = result.get('values', [])
        row_position = len(rows) + 1

        sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={
            "requests": [{
                "insertRange": {
                    "range": {"sheetId": sheet_id, "startRowIndex": row_position - 1, "endRowIndex": row_position},
                    "shiftDimension": "ROWS"
                }
            }]
        }).execute()

        sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!A{row_position}",
                              valueInputOption="RAW", body={"values": [["End of Week"]]}).execute()

        color_request = {
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_position - 1,
                        "endRowIndex": row_position,
                        "startColumnIndex": 0,
                        "endColumnIndex": 11
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 1.0, "green": 0.8, "blue": 0.8}
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }]
        }
        sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body=color_request).execute()

        headers = ["Date", "Match", "Amount", "Platform", "Odds", "Correct Odds", "Profit", "Win/Lose", "Outcome $", "Peso", "TXT 2% COMS"]
        sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f"{current_month}!A{row_position + 1}",
                              valueInputOption="RAW", body={"values": [headers]}).execute()

        header_format_request = {
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_position,
                        "endRowIndex": row_position + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 11
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 1.0, "green": 0.8, "blue": 0.6},
                            "textFormat": {"bold": True}
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)"
                }
            }]
        }
        sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body=header_format_request).execute()

        logging.info("End of week marker and headers added successfully.")
        await update.message.reply_text("End of Week marker and headers added successfully.")

    except Exception as e:
        logging.error(f"Error adding End of Week marker and headers: {e}")
        await update.message.reply_text("An error occurred while adding the End of Week marker and headers.")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bet", bet))
    application.add_handler(CommandHandler("end", end_of_week))
    application.run_polling()

if __name__ == "__main__":
    main()