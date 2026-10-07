"""
PDF generator for transcripts.
Creates formatted PDF documents from transcript text files.
"""

from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from config import Config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class PDFGenerator:
    """Generate PDF documents from transcript text files"""
    
    def __init__(self, page_size=letter):
        """
        Initialize PDF generator.
        
        Args:
            page_size: Page size (letter or A4)
        """
        self.page_size = page_size
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Set up custom paragraph styles with premium book-like typography"""
        # Title style - elegant and prominent
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=26,
            textColor='#000000',
            spaceAfter=36,
            spaceBefore=24,
            alignment=TA_CENTER,
            fontName='Times-Bold',
            leading=32
        ))
        
        # Subtitle style - refined metadata
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor='#666666',
            spaceAfter=48,
            alignment=TA_CENTER,
            fontName='Times-Italic'
        ))
        
        # Body style - optimized for long-form reading like a novel
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['Normal'],
            fontSize=13,              # Larger for comfortable reading
            leading=22,               # Generous line spacing (1.7x)
            textColor='#000000',      # Pure black for clarity
            alignment=TA_LEFT,        # Justified text like books
            fontName='Times-Roman',
            spaceAfter=16,            # Space between paragraphs
            firstLineIndent=0,        # No indent for cleaner look
            leftIndent=0,
            rightIndent=0
        ))
    
    def generate_pdf(self, transcript_path: Path, output_path: Path = None) -> Path:
        """
        Generate a PDF from a transcript file.
        
        Args:
            transcript_path: Path to the transcript text file
            output_path: Optional output path for PDF (auto-generated if None)
        
        Returns:
            Path to the generated PDF file
        """
        try:
            if not transcript_path.exists():
                raise FileNotFoundError(f"Transcript not found: {transcript_path}")
            
            # Read transcript content
            with open(transcript_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Generate output path if not provided
            if output_path is None:
                output_path = Config.PDF_DIR / f"{transcript_path.stem}.pdf"
            
            # Create PDF with book-like margins
            doc = SimpleDocTemplate(
                str(output_path),
                pagesize=self.page_size,
                rightMargin=1.0*inch,      # Generous margins like a book
                leftMargin=1.0*inch,
                topMargin=1.0*inch,
                bottomMargin=1.0*inch
            )
            
            # Build content
            story = []
            
            # Add title
            title = transcript_path.stem.replace('_transcript', '').replace('_', ' ')
            story.append(Paragraph(title, self.styles['CustomTitle']))
            
            # Add metadata
            date_str = datetime.now().strftime("%B %d, %Y")
            story.append(Paragraph(f"Generated on {date_str}", self.styles['CustomSubtitle']))
            story.append(Spacer(1, 0.3*inch))
            
            # Add transcript content
            # Split into paragraphs for better formatting
            paragraphs = content.split('\n\n')
            
            for para in paragraphs:
                if para.strip():
                    # Clean up the text
                    clean_text = para.strip().replace('\n', ' ')
                    # Escape special characters for reportlab
                    clean_text = clean_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(clean_text, self.styles['CustomBody']))
                    story.append(Spacer(1, 0.1*inch))
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"Generated PDF: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            raise
    
    def batch_generate_pdfs(self, transcript_dir: Path = None) -> list[Path]:
        """
        Generate PDFs for all transcripts in a directory.
        
        Args:
            transcript_dir: Directory containing transcripts (uses Config.TRANSCRIPTS_DIR if None)
        
        Returns:
            List of paths to generated PDF files
        """
        transcript_dir = transcript_dir or Config.TRANSCRIPTS_DIR
        
        if not transcript_dir.exists():
            logger.warning(f"Transcript directory not found: {transcript_dir}")
            return []
        
        pdf_paths = []
        transcript_files = list(transcript_dir.glob('*.txt'))
        
        logger.info(f"Generating PDFs for {len(transcript_files)} transcripts")
        
        for transcript_path in transcript_files:
            try:
                pdf_path = self.generate_pdf(transcript_path)
                pdf_paths.append(pdf_path)
            except Exception as e:
                logger.error(f"Failed to generate PDF for {transcript_path.name}: {e}")
        
        logger.info(f"Generated {len(pdf_paths)} PDFs")
        return pdf_paths
