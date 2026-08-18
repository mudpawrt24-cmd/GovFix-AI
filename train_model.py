"""
GovFix AI - Lightweight Pure-Python Model Trainer
Generates 'govfix_model.json' in <0.01 seconds.
Zero external C-library dependencies (runs natively on Python 3.10 - 3.14).
"""

import json
import math
import re
from collections import Counter

TRAINING_DATA = [
    # 1. Document Upload Errors
    ("ERROR_413_FILE_TOO_LARGE: Uploaded land record exceeds 100KB threshold", "DOC_OVERSIZE"),
    ("Upload rejected request entity exceeds file limit 100kb", "DOC_OVERSIZE"),
    ("INVALID_MIME_TYPE: Only image/jpeg or application/pdf permitted", "DOC_INVALID_FORMAT"),
    ("CORRUPTED_PDF_HEADER: Document rejected during digital signature parsing", "DOC_CORRUPT"),
    
    # 2. Session / Form Dropped Errors
    ("HTTP 419 Authentication Timeout: CSRF token mismatch on submission", "SESSION_TIMEOUT"),
    ("SESSION_INVALID_0x889: User state lost during multi-step registration", "SESSION_TIMEOUT"),
    ("INACTIVE_USER_TOKEN: Session expired after idle time", "SESSION_TIMEOUT"),
    
    # 3. Payment & DBT Desync Errors
    ("DBT_GATEWAY_TIMEOUT_504: NPCI Aadhar bridge desynchronization error", "PAYMENT_DESYNC"),
    ("ERR_PAYMENT_TXN_PENDING: Bank debited but merchant ledger unconfirmed", "PAYMENT_PENDING"),
    ("Bank account debited but NPCI DBT ledger confirmation is pending", "PAYMENT_PENDING"),
    
    # 4. Format / Land Registry Validation Errors
    ("REGEX_MISMATCH_KHASRA: Land record Khata/Khasra number format invalid", "KHASRA_FORMAT_ERR"),
    ("Land record Khata Khasra number does not match district revenue registry pattern", "KHASRA_FORMAT_ERR"),
    
    # 5. Server Concurrency & 5xx Overload
    ("HTTP 503 SERVICE UNAVAILABLE: NIC State Data Center server queue maxed", "SERVER_OVERLOAD"),
    ("GATEWAY_TIMEOUT_504: Upstream Land Records DB server unreachable", "SERVER_OVERLOAD"),
    
    # 6. Complex Disputed Registry (Escalation to Admin)
    ("LAND_RECORD_LOCKED_DISPUTE: Khata number flagged under active tehsil registry dispute", "ADMIN_ESCALATION_REQUIRED"),
    ("MANUAL_VERIFICATION_MANDATED: District revenue officer signature required", "ADMIN_ESCALATION_REQUIRED")
]

RESOLUTION_KNOWLEDGE_BASE = {
    "DOC_OVERSIZE": {
        "action_type": "CLIENT_AUTO_COMPRESS",
        "en": "Your document exceeds the 100 KB limit. GovFix AI will compress it without quality loss.",
        "hi": "दस्तावेज़ का आकार 100 KB से अधिक है। GovFix AI इसे बिना गुणवत्ता खोए कंप्रेस कर देगा।"
    },
    "DOC_INVALID_FORMAT": {
        "action_type": "CLIENT_AUTO_CONVERT",
        "en": "The portal only accepts PDF or JPEG files. Please select a valid document.",
        "hi": "पोर्टल केवल PDF या JPEG फ़ाइलों को स्वीकार करता है।"
    },
    "SESSION_TIMEOUT": {
        "action_type": "RESTORE_FORM_DRAFT",
        "en": "Session timed out, but GovFix AI securely cached your data. Click below to restore.",
        "hi": "सत्र समाप्त हो गया, लेकिन आपका डेटा सुरक्षित है। पुनर्स्थापित करने के लिए नीचे क्लिक करें।"
    },
    "PAYMENT_PENDING": {
        "action_type": "RECONCILE_PAYMENT",
        "en": "Money was deducted from your bank. DO NOT pay again. We are polling NPCI for confirmation.",
        "hi": "बैंक से राशि कट गई है। कृपया दोबारा भुगतान न करें। हम पुष्टि की जांच कर रहे हैं।"
    },
    "KHASRA_FORMAT_ERR": {
        "action_type": "AUTO_FORMAT_INPUT",
        "en": "Khasra number must follow standard format (e.g., '142/9'). Click below to auto-format.",
        "hi": "खसरा संख्या '142/9' जैसे प्रारूप में होनी चाहिए। स्वतः सुधार के लिए नीचे क्लिक करें।"
    },
    "SERVER_OVERLOAD": {
        "action_type": "AUTO_QUEUE_RETRY",
        "en": "Server is experiencing peak traffic. GovFix AI has queued your submission for auto-retry.",
        "hi": "सर्वर पर अत्यधिक लोड है। GovFix AI ने आपके फॉर्म को कतार में जोड़ दिया है।"
    },
    "ADMIN_ESCALATION_REQUIRED": {
        "action_type": "ESCALATE_TO_ADMIN",
        "en": "This requires manual clearance. We have escalated this to the Tehsil Admin Control Room.",
        "hi": "इस समस्या के लिए अधिकारी सत्यापन की आवश्यकता है। हमने इसे एडमिन कंट्रोल रूम को भेज दिया है।"
    }
}

def tokenize(text: str):
    words = re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower())
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i+1]}")
    return tokens

def train():
    print("[GovFix AI] Training Pure-Python TF-IDF Engine...")
    doc_count = len(TRAINING_DATA)
    df = Counter()
    tokenized_docs = []

    for text, label in TRAINING_DATA:
        tokens = set(tokenize(text))
        for t in tokens:
            df[t] += 1
        tokenized_docs.append((tokenize(text), label))

    idf = {term: math.log((doc_count + 1) / (count + 1)) + 1.0 for term, count in df.items()}

    trained_docs = []
    for tokens, label in tokenized_docs:
        tf = Counter(tokens)
        vec = {term: count * idf.get(term, 1.0) for term, count in tf.items()}
        length = math.sqrt(sum(v ** 2 for v in vec.values())) or 1.0
        norm_vec = {k: v / length for k, v in vec.items()}
        trained_docs.append({"vector": norm_vec, "label": label})

    model_payload = {
        "idf": idf,
        "docs": trained_docs,
        "resolutions": RESOLUTION_KNOWLEDGE_BASE
    }

    with open("govfix_model.json", "w", encoding="utf-8") as f:
        json.dump(model_payload, f, indent=2, ensure_ascii=False)

    print("✅ [GovFix AI] Model trained and exported to 'govfix_model.json' successfully!")

if __name__ == "__main__":
    train()