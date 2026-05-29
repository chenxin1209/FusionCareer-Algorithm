"""
Resume parser: extract text from PDF/DOCX, structure via DeepSeek, export CSV for fc_user_profile / fc_resume.
"""

from resume_parser.parser import FIELD_NAMES, ResumeParser

__all__ = ["ResumeParser", "FIELD_NAMES", "__version__"]

__version__ = "1.0.0"
