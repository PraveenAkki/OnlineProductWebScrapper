# ImageCompare - All Phases Setup

## Install

```powershell
# Step 1 - PyTorch CPU
python -m pip install torch==2.3.1+cpu torchvision==0.18.1+cpu --index-url https://download.pytorch.org/whl/cpu

# Step 2 - Everything else
python -m pip install -r requirements.txt

# Step 3 - Database
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## .env File Setup (for Google Lens)
Create file: D:\imagecompare\.env
Add this line:
  SERPAPI_KEY=your_key_here

Get free key at: https://serpapi.com/ (100 searches/month free)

## API Endpoints

| Endpoint | Phase | Description | Cost |
|---|---|---|---|
| POST /api/upload/ | set in settings.py | uses CLASSIFIER_PHASE | free |
| POST /api/upload/fashion-clip/ | 4A | FashionCLIP always | free |
| POST /api/upload/google-lens/ | 4B | Google Lens always | 100/month free |
| GET /api/searches/ | - | list all searches | - |
| GET /api/searches/<id>/ | - | detail + products | - |
| GET /api/phase/ | - | show all phases | - |

## Switch Default Phase (settings.py)

CLASSIFIER_PHASE = 'mobilenet'     # Phase 1+2 - fast, basic
CLASSIFIER_PHASE = 'clip'          # Phase 3   - better
CLASSIFIER_PHASE = 'fashion_clip'  # Phase 4A  - best for fashion (free)
CLASSIFIER_PHASE = 'google_lens'   # Phase 4B  - most accurate (needs API key)

## What each phase returns for a red saree image

Phase 1 (mobilenet):   "silk saree"
Phase 2 (+color):      "red silk saree"
Phase 3 (clip):        "red silk saree with golden border"
Phase 4A (fashion):    "women red floral print silk saree"
Phase 4B (google):     "Banarasi Red Silk Saree with Zari Work" (exact)
