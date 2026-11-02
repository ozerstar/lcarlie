"""MOY's Uyumsoft e-Fatura web service: READ ONLY (owner, 02.11.2026).

Only list / data / identity calls are allowed here. Sending, accepting, rejecting or
marking invoices as taken (SendInvoice, SendDocumentResponse, SetInvoicesTaken, …) would
change what MOY's accountant sees, so those operations are refused by name.
"""
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree
from xml.sax.saxutils import escape

# Uyumsoft's own list (owner, 02.11.2026); efatura.uyumsoft.com.tr refuses this user
URL = "https://edonusumapi.uyum.com.tr/Services/Integration"
CREDENTIALS = "/etc/lcarlie/uyumsoft.env"
READ_ONLY = {"WhoAmI", "TestConnection", "GetInboxInvoiceList", "GetOutboxInvoiceList",
             "GetInboxInvoiceData", "GetOutboxInvoiceData"}
_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
_WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"


class UyumsoftError(Exception):
    pass


def _credentials(path=CREDENTIALS):
    values = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            key, sep, value = line.strip().partition("=")
            if sep:
                values[key.strip()] = value.strip()
    if not values.get("UYUMSOFT_USER") or not values.get("UYUMSOFT_PASS"):
        raise UyumsoftError("uyumsoft.env içinde UYUMSOFT_USER ve UYUMSOFT_PASS olmalı.")
    return values["UYUMSOFT_USER"], values["UYUMSOFT_PASS"]


def envelope(action, body, user, password, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = "%Y-%m-%dT%H:%M:%S.000Z"
    return f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:u="{_WSU}">
<s:Header><o:Security s:mustUnderstand="1" xmlns:o="{_WSSE}">
<u:Timestamp u:Id="_0"><u:Created>{now.strftime(stamp)}</u:Created><u:Expires>{(now + timedelta(minutes=5)).strftime(stamp)}</u:Expires></u:Timestamp>
<o:UsernameToken u:Id="uuid-{uuid.uuid4()}-1"><o:Username>{escape(user)}</o:Username>
<o:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{escape(password)}</o:Password></o:UsernameToken>
</o:Security></s:Header>
<s:Body><{action} xmlns="http://tempuri.org/">{body}</{action}></s:Body></s:Envelope>"""


def call(action, body="", *, timeout=60):
    if action not in READ_ONLY:
        raise UyumsoftError(f"{action} okuma işlemi değil; Uyumsoft'ta hiçbir şey değiştirilmez.")
    user, password = _credentials()
    request = urllib.request.Request(URL, data=envelope(action, body, user, password).encode("utf-8"), headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"http://tempuri.org/IIntegration/{action}"'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return ElementTree.fromstring(response.read())
    except urllib.error.HTTPError as exc:  # a SOAP fault comes back as HTTP 500 with a readable reason
        text = exc.read().decode("utf-8", "replace")
        reason = ElementTree.fromstring(text).findtext(".//faultstring") if text.lstrip().startswith("<") else ""
        raise UyumsoftError(f"Uyumsoft {exc.code}: {reason or text[:200]}") from None


def whoami():
    """Proves the user/password work; returns the company name and VKN Uyumsoft knows."""
    root = call("WhoAmI")
    flat = {element.tag.rsplit("}", 1)[-1]: (element.text or "").strip() for element in root.iter()}
    if flat.get("IsSucceded", flat.get("IsSucceeded", "true")).lower() == "false":
        raise UyumsoftError(flat.get("Message") or "Uyumsoft girişi kabul etmedi.")
    return {key: value for key, value in flat.items() if value and key not in {"Envelope", "Body", "Header"}}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def invoice_list(box, start, end, *, page=0, size=100, scenario="eInvoice"):
    """One page of MOY's incoming ("inbox") or outgoing ("outbox") invoices created in [start, end]."""
    nil = ' xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:nil="true"'
    newest = ' OnlyNewestInvoices="false"' if box == "inbox" else ""
    body = (f'<query PageIndex="{int(page)}" PageSize="{int(size)}"{newest}>'
            f'<ExecutionStartDate{nil}/><ExecutionEndDate{nil}/>'
            f'<CreateStartDate>{start:%Y-%m-%dT00:00:00}</CreateStartDate><CreateEndDate>{end:%Y-%m-%dT23:59:59}</CreateEndDate>'
            f'<Status{nil}/><SortColumn>CreateDate</SortColumn><SortMode>Ascending</SortMode><IsArchived{nil}/>'
            f'<IncludeTagList>false</IncludeTagList>'
            + (f'<Scenario>{scenario}</Scenario>' if box == "outbox" else "") + '</query>')
    root = call("GetInboxInvoiceList" if box == "inbox" else "GetOutboxInvoiceList", body)
    result = next(e for e in root.iter() if _local(e.tag).endswith("InvoiceListResult"))
    if (result.get("IsSucceded") or "true").lower() == "false":
        raise UyumsoftError(result.get("Message") or "Uyumsoft listeyi vermedi.")
    value = next((e for e in result if _local(e.tag) == "Value"), None)
    items = [] if value is None else [
        {_local(field.tag): (field.text or "").strip() for field in item}
        for item in value.iter() if _local(item.tag) == "Items"]
    return {"page": dict(value.attrib) if value is not None else {}, "items": items}


def invoice_ubl(box, invoice_id):
    """The e-Fatura UBL XML itself: every line with its name, quantity, price and VAT."""
    import base64
    root = call("GetInboxInvoiceData" if box == "inbox" else "GetOutboxInvoiceData",
                f"<invoiceId>{escape(invoice_id)}</invoiceId>")
    data = next((e.text for e in root.iter() if _local(e.tag) == "Data"), None)
    if not data:
        raise UyumsoftError("Fatura içeriği boş geldi.")
    return base64.b64decode(data)


if __name__ == "__main__" and sys.argv[1:] == ["test"]:
    try:
        info = whoami()
    except (OSError, UyumsoftError, ElementTree.ParseError) as exc:
        print("BAĞLANAMADIM:", exc)
        sys.exit(1)
    print("BAĞLANDI. Uyumsoft'un tanıdığı bilgiler:")
    for key, value in info.items():
        print(f"  {key}: {value}"[:160])
