"""
Tab Constellation — Onboarding
================================
Generates personalized domain rules from user profile.
Saved to data/user_profile.json, loaded by ingest_realtime.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

PROFILE_PATH = Path(__file__).parent.parent / "data" / "user_profile.json"

# ── Preset profiles ────────────────────────────────────────────
PRESET_PROFILES: dict[str, dict] = {
    "software_engineer": {
        "extra_domains": {
            "leetcode.com": "work",
            "hackerrank.com": "work",
            "codeforces.com": "work",
            "replit.com": "work",
            "codesandbox.io": "work",
            "vercel.com": "work",
            "netlify.com": "work",
            "railway.app": "work",
            "render.com": "work",
            "fly.io": "work",
            "supabase.com": "work",
            "planetscale.com": "work",
        },
        "extra_focus_signals": [
            "debugging", "deployment", "ci/cd", "pull request",
            "code review", "refactor", "unit test", "integration",
            "microservice", "containerize", "pipeline",
        ],
    },
    "researcher_student": {
        "extra_domains": {
            "jstor.org": "research",
            "springer.com": "research",
            "sciencedirect.com": "research",
            "acm.org": "research",
            "ieee.org": "research",
            "overleaf.com": "work",
            "zotero.org": "work",
            "mendeley.com": "work",
            "scholar.google.com": "research",
            "ssrn.com": "research",
            "nature.com": "research",
            "cell.com": "research",
            "plos.org": "research",
        },
        "extra_focus_signals": [
            "abstract", "methodology", "literature review",
            "citation", "hypothesis", "experiment", "findings",
            "peer reviewed", "doi", "preprint", "journal",
            "thesis", "dissertation", "conference paper",
        ],
    },
    "designer": {
        "extra_domains": {
            "sketch.com": "creative",
            "invisionapp.com": "creative",
            "zeplin.io": "creative",
            "coolors.co": "creative",
            "fonts.google.com": "creative",
            "unsplash.com": "creative",
            "awwwards.com": "creative",
            "mobbin.com": "creative",
            "lottiefiles.com": "creative",
            "spline.design": "creative",
            "rive.app": "creative",
            "maze.co": "work",
            "hotjar.com": "work",
        },
        "extra_focus_signals": [
            "design system", "wireframe", "prototype", "user flow",
            "color palette", "typography", "accessibility", "component",
            "figma", "sketch", "mockup", "user research", "usability",
        ],
    },
    "finance_business": {
        "extra_domains": {
            "wsj.com": "finance",
            "ft.com": "finance",
            "seekingalpha.com": "finance",
            "morningstar.com": "finance",
            "finviz.com": "finance",
            "macrotrends.net": "finance",
            "statista.com": "research",
            "hbr.org": "research",
            "mckinsey.com": "research",
            "bain.com": "research",
            "deloitte.com": "research",
            "pitchbook.com": "finance",
            "crunchbase.com": "finance",
        },
        "extra_focus_signals": [
            "revenue", "earnings", "quarterly", "fiscal",
            "portfolio", "market cap", "valuation", "roi",
            "cash flow", "balance sheet", "p&l", "ebitda",
            "venture capital", "fundraising", "Series A",
        ],
    },
    "healthcare": {
        "extra_domains": {
            "uptodate.com": "health",
            "medscape.com": "health",
            "nejm.org": "research",
            "thelancet.com": "research",
            "bmj.com": "research",
            "drugs.com": "health",
            "rxlist.com": "health",
            "medlineplus.gov": "health",
            "epocrates.com": "health",
            "radiopaedia.org": "reference",
            "amboss.com": "health",
            "clinicalkey.com": "research",
        },
        "extra_focus_signals": [
            "diagnosis", "treatment", "clinical", "patient",
            "symptoms", "dosage", "contraindication", "prognosis",
            "evidence based", "randomized controlled", "cohort",
            "meta-analysis", "systematic review", "guidelines",
        ],
    },
}

# ── Topic → domain map ─────────────────────────────────────────
TOPIC_DOMAIN_MAP: dict[str, dict[str, str]] = {
    "machine learning": {
        "kaggle.com": "research",
        "fast.ai": "research",
        "distill.pub": "research",
        "machinelearningmastery.com": "research",
        "deeplearning.ai": "research",
    },
    "python": {
        "pypi.org": "reference",
        "realpython.com": "research",
        "python.org": "reference",
        "pydantic.dev": "reference",
    },
    "javascript": {
        "javascript.info": "research",
        "npmjs.com": "reference",
        "babeljs.io": "reference",
        "webpack.js.org": "reference",
        "vitejs.dev": "reference",
    },
    "devops": {
        "grafana.com": "work",
        "prometheus.io": "reference",
        "terraform.io": "reference",
        "ansible.com": "reference",
        "jenkins.io": "reference",
        "circleci.com": "work",
    },
    "data science": {
        "kaggle.com": "research",
        "towardsdatascience.com": "research",
        "analyticsvidhya.com": "research",
        "datacamp.com": "research",
        "mode.com": "work",
    },
    "web development": {
        "css-tricks.com": "reference",
        "smashingmagazine.com": "research",
        "web.dev": "reference",
        "caniuse.com": "reference",
        "tailwindcss.com": "reference",
    },
    "security": {
        "owasp.org": "reference",
        "exploit-db.com": "research",
        "cve.mitre.org": "reference",
        "hackerone.com": "work",
        "bugcrowd.com": "work",
        "snyk.io": "work",
    },
    "qdrant": {
        "qdrant.tech": "research",
        "cloud.qdrant.io": "work",
    },
    "golang": {
        "go.dev": "reference",
        "pkg.go.dev": "reference",
        "gobyexample.com": "research",
    },
    "rust": {
        "doc.rust-lang.org": "reference",
        "crates.io": "reference",
        "rustup.rs": "reference",
    },
    "react": {
        "react.dev": "reference",
        "reactrouter.com": "reference",
        "redux.js.org": "reference",
    },
    "ai": {
        "arxiv.org": "research",
        "huggingface.co": "research",
        "openai.com": "research",
        "anthropic.com": "research",
        "paperswithcode.com": "research",
    },
    "blockchain": {
        "ethereum.org": "research",
        "docs.soliditylang.org": "reference",
        "hardhat.org": "reference",
        "opensea.io": "shopping",
    },
}


# ── Models ─────────────────────────────────────────────────────

class OnboardingRequest(BaseModel):
    preset: str = ""
    topics: list[str] = []
    custom_domains: dict[str, str] = {}


class OnboardingResponse(BaseModel):
    profile_saved: bool
    domain_rules_count: int
    focus_signals_count: int
    message: str


# ── Routes ─────────────────────────────────────────────────────

@router.post("/setup", response_model=OnboardingResponse)
def setup_profile(req: OnboardingRequest) -> OnboardingResponse:
    profile: dict = {
        "preset": req.preset,
        "topics": req.topics,
        "custom_domains": req.custom_domains,
        "extra_domains": {},
        "extra_focus_signals": [],
    }

    # Apply preset
    if req.preset and req.preset in PRESET_PROFILES:
        preset = PRESET_PROFILES[req.preset]
        profile["extra_domains"].update(preset["extra_domains"])
        profile["extra_focus_signals"].extend(preset["extra_focus_signals"])

    # Apply custom domains
    profile["extra_domains"].update(req.custom_domains)

    # Apply topic-based domains
    for topic in req.topics:
        t = topic.lower().strip()
        for key, domains in TOPIC_DOMAIN_MAP.items():
            if key in t or t in key:
                profile["extra_domains"].update(domains)

    # Save
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)

    return OnboardingResponse(
        profile_saved=True,
        domain_rules_count=len(profile["extra_domains"]),
        focus_signals_count=len(profile["extra_focus_signals"]),
        message=f"Profile saved with {len(profile['extra_domains'])} domain rules",
    )


@router.get("/profile")
def get_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {"exists": False}
    with open(PROFILE_PATH) as f:
        return {"exists": True, "profile": json.load(f)}


@router.get("/presets")
def get_presets() -> dict:
    return {
        "presets": [
            {"id": "software_engineer",  "label": "💻 Software Engineer",    "description": "Code, DevOps, open source"},
            {"id": "researcher_student", "label": "🔬 Researcher / Student", "description": "Papers, citations, academic"},
            {"id": "designer",           "label": "🎨 Designer",             "description": "Figma, design systems, inspiration"},
            {"id": "finance_business",   "label": "📈 Finance / Business",   "description": "Markets, strategy, BI"},
            {"id": "healthcare",         "label": "🏥 Healthcare",           "description": "Clinical refs, research, guidelines"},
        ]
    }
