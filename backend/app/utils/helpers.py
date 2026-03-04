import re
from typing import Optional
from io import BytesIO
from loguru import logger


def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF using basic methods"""
    try:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return ""


def extract_text_from_docx(file_content: bytes) -> str:
    """Extract text from DOCX file"""
    try:
        from docx import Document
        doc = Document(BytesIO(file_content))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting DOCX text: {e}")
        return ""


def extract_text_from_txt(file_content: bytes) -> str:
    """Extract text from plain text file"""
    try:
        return file_content.decode('utf-8').strip()
    except Exception as e:
        logger.error(f"Error extracting text: {e}")
        return ""


def get_file_type(filename: str) -> str:
    """Determine file type from filename"""
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    if ext in ['pdf']:
        return 'pdf'
    elif ext in ['docx', 'doc']:
        return 'docx'
    elif ext in ['txt', 'text']:
        return 'txt'
    elif ext in ['md', 'markdown']:
        return 'markdown'
    else:
        return 'txt'


def process_file_content(filename: str, content: bytes) -> str:
    """Process file and extract text based on file type"""
    file_type = get_file_type(filename)
    
    if file_type == 'pdf':
        return extract_text_from_pdf(content)
    elif file_type == 'docx':
        return extract_text_from_docx(content)
    else:
        return extract_text_from_txt(content)


def clean_text(text: str) -> str:
    """Clean and normalize text"""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    text = text.strip()
    return text


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences"""
    sentence_endings = r'(?<=[.!?])\s+'
    sentences = re.split(sentence_endings, text)
    return [s.strip() for s in sentences if s.strip()]


def truncate_text(text: str, max_length: int = 10000) -> str:
    """Truncate text to maximum length"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
