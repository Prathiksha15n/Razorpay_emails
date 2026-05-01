/**
 * Google Apps Script — Web App for Razorpay → Google Sheet sync.
 *
 * Deploy: Deploy → New deployment → Web app → Execute as: Me, Who has access: Anyone
 * Copy the web app URL into GOOGLE_SHEETS_WEBAPP_URL (Django / Render).
 *
 * Sheet columns (row 1 headers): Payment ID | Email | Name | Amount | Date | status
 * Must match the JSON keys sent by Django (payments.views._save_payment_to_google_sheet).
 */
const SHEET_ID = "13As_C_gAPmfnEsvMQRzqg_KPbB7Ah9Lq_QE9um5_wFU";
const SHEET_NAME = "Sheet1";

function getSheet() {
  return SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
}

function doGet(e) {
  const sheet = getSheet();
  const paymentIdToCheck = e.parameter.check_payment_id;

  if (!paymentIdToCheck) {
    return ContentService.createTextOutput(
      JSON.stringify({ error: "No payment id provided" })
    ).setMimeType(ContentService.MimeType.JSON);
  }

  const data = sheet.getDataRange().getValues();
  const want = String(paymentIdToCheck).trim();

  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]).trim() === want) {
      return ContentService.createTextOutput(
        JSON.stringify({ exists: true })
      ).setMimeType(ContentService.MimeType.JSON);
    }
  }

  return ContentService.createTextOutput(
    JSON.stringify({ exists: false })
  ).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const sheet = getSheet();
    if (!e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(
        JSON.stringify({ success: false, error: "No POST body" })
      ).setMimeType(ContentService.MimeType.JSON);
    }

    const data = JSON.parse(e.postData.contents);

    // Order MUST match headers: Payment ID, Email, Name, Amount, Date, status
    const rowDate = data.date
      ? new Date(data.date)
      : new Date();

    sheet.appendRow([
      data.payment_id,
      data.email,
      data.name,
      data.amount,
      rowDate,
      data.status,
    ]);

    return ContentService.createTextOutput(
      JSON.stringify({ success: true })
    ).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({
        success: false,
        error: String(err.message || err),
      })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}
