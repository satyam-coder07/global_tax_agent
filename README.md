# Global Agentic Tax Hub

A high-stakes Chartered Accountant-grade tax optimization platform covering US, UK, and India jurisdictions. It performs deterministic 2026 tax scenario math natively, supports OCR document parsing, parses exact Double Taxation Avoidance Agreements (DTAA), and uses a BYOK methodology for multi-provider LLM integrations (OpenAI, Anthropic, Google, Groq) to provide advanced reasoning.

## Tech Stack
- Frontend: Streamlit, Plotly (Glassmorphism layout)
- Backend Engine: Python 3, Pandas, Pydantic
- Document OCR: pdfplumber, pytesseract, Pillow
- AI Agents: OpenAI, Anthropic, Google Gemini, Groq (via LLMBridge)
- Scraper: Exa (Dynamic Government Tax Act lookup) 

## How to Run

1. Clone the repository and navigate to the project root.
2. Install the necessary system dependencies (ensure `tesseract` is installed on your OS for image parsing).
3. Install Python requirements:
```bash
pip install -r requirements.txt
```
4. Boot the internal server:
```bash
streamlit run app.py
```
5. Navigate to `localhost:8501`. Provide your own LLM API key inside the setup sidebar to activate CA automated analytics.
