"""
Main Gradio application for BBC Audio Scraper.
Provides web interface for downloading and transcribing BBC audio.
"""

import gradio as gr
import base64
from pathlib import Path
from config import Config
from src.scraper.rss_scraper import RSScraper
from src.scraper.get_iplayer_wrapper import GetIPlayerWrapper
from src.transcription.transcriber import WhisperTranscriber
from src.transcription.audio_processor import AudioProcessor
from src.utils.file_manager import FileManager
from src.utils.pdf_generator import PDFGenerator
from src.utils.logger import setup_logger
from src.utils.history_manager import HistoryManager
from src.utils.topic_categorizer import TopicCategorizer

logger = setup_logger(__name__)

# Initialize components
rss_scraper = RSScraper()
iplayer = GetIPlayerWrapper()
transcriber = WhisperTranscriber()
audio_processor = AudioProcessor()
file_manager = FileManager()
pdf_generator = PDFGenerator()
history_manager = HistoryManager()
topic_categorizer = TopicCategorizer()

# Categorize all audio files on startup (commented out to avoid API quota issues)
# logger.info("Starting topic categorization...")
# topic_categorizer.categorize_all_files(file_manager.list_audio_files())
# logger.info("Topic categorization complete!")

# ============================================================================
# TAB 1: DOWNLOAD AUDIO
# ============================================================================

def download_from_rss(feed_url: str, limit: int):
    """Download episodes from RSS feed"""
    try:
        if not feed_url:
            return "Please enter an RSS feed URL"

        limit = int(limit) if limit else None
        files = rss_scraper.download_episodes(feed_url, limit)

        if files:
            return f"Downloaded {len(files)} episode(s):\n" + "\n".join([f"- {f.name}" for f in files])
        else:
            return "No episodes downloaded. Check the feed URL."
    except Exception as e:
        return f"Error: {str(e)}"

def download_with_iplayer(query: str):
    """Search and download with get_iplayer"""
    try:
        if not query:
            return "Please enter a search query or URL"

        # Check if it's a URL or search query
        if query.startswith('http'):
            success = iplayer.download_by_url(query)
            if success:
                return f"Downloaded from URL: {query}"
            else:
                return "Download failed. Check logs for details."
        else:
            # Search for programmes
            results = iplayer.search(query)
            if not results:
                return f"No programmes found for: {query}"

            # Show first 5 results
            output = f"Found {len(results)} programme(s):\n\n"
            for i, prog in enumerate(results[:5], 1):
                output += f"{i}. {prog['name']} - {prog['episode']}\n"
                output += f"   PID: {prog['pid']}\n\n"

            output += "\nTo download, use the PID with format: pid:<PID>"
            return output
    except Exception as e:
        return f"Error: {str(e)}"

def list_downloads():
    """List downloaded audio files"""
    files = file_manager.list_audio_files()
    if files:
        return "\n".join([f.name for f in files])
    return "No audio files found"

def get_popular_feeds():
    """Get list of popular BBC feeds"""
    feeds = rss_scraper.list_available_feeds()
    output = "Popular BBC Podcast Feeds:\n\n"
    for name, url in feeds.items():
        output += f"**{name.replace('_', ' ').title()}**\n{url}\n\n"
    return output

# ============================================================================
# TAB 2: TRANSCRIBE
# ============================================================================

def transcribe_file(audio_file, model_size: str, language: str):
    """Transcribe a single audio file"""
    try:
        if not audio_file:
            return "Please select an audio file"

        # Update model if changed
        if model_size != transcriber.model_size:
            transcriber.model_size = model_size
            transcriber.model = None  # Force reload

        # Transcribe
        transcript_path = transcriber.transcribe_and_save(Path(audio_file), language)

        if transcript_path:
            return f"Transcription complete!\nSaved to: {transcript_path.name}"
        else:
            return "Transcription failed"
    except Exception as e:
        return f"Error: {str(e)}"

def transcribe_all(model_size: str, language: str):
    """Transcribe all audio files"""
    try:
        audio_files = file_manager.list_audio_files()
        if not audio_files:
            return "No audio files found to transcribe"

        # Update model if changed
        if model_size != transcriber.model_size:
            transcriber.model_size = model_size
            transcriber.model = None

        transcripts = transcriber.batch_transcribe(audio_files, language)

        return f"Transcribed {len(transcripts)}/{len(audio_files)} files successfully!"
    except Exception as e:
        return f"Error: {str(e)}"

def list_transcripts():
    """List all transcripts"""
    transcripts = file_manager.list_transcripts()
    if transcripts:
        return "\n".join([t.name for t in transcripts])
    return "No transcripts found"

def load_transcript(transcript_name: str):
    """Load a transcript for viewing"""
    try:
        transcript_path = Config.TRANSCRIPTS_DIR / transcript_name
        if transcript_path.exists():
            with open(transcript_path, 'r', encoding='utf-8') as f:
                return f.read()
        return "Transcript not found"
    except Exception as e:
        return f"Error: {str(e)}"

def export_transcript_to_pdf(transcript_name: str):
    """Export a single transcript to PDF"""
    try:
        if not transcript_name:
            return "Please select a transcript", None

        transcript_path = Config.TRANSCRIPTS_DIR / transcript_name
        if not transcript_path.exists():
            return "Transcript not found", None

        # Generate PDF
        pdf_path = pdf_generator.generate_pdf(transcript_path)

        return f"PDF generated successfully!\nSaved to: {pdf_path.name}", str(pdf_path)
    except Exception as e:
        return f"Error: {str(e)}", None

def export_all_transcripts_to_pdf():
    """Export all transcripts to PDF"""
    try:
        transcripts = file_manager.list_transcripts()
        if not transcripts:
            return "No transcripts found to export"

        pdf_paths = pdf_generator.batch_generate_pdfs()

        if pdf_paths:
            return f"Generated {len(pdf_paths)} PDF(s) successfully!\n\nPDFs saved in: pdfs/"
        else:
            return "No PDFs were generated"
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================================
# TAB 3: PDF READER
# ============================================================================

def get_available_content():
    """Get list of available audio files and their corresponding PDFs/transcripts"""
    audio_files = file_manager.list_audio_files()
    completed_names = history_manager.get_completed_content_names()
    content_list = []
    
    for audio_file in audio_files:
        # Get base name without extension
        base_name = audio_file.stem
        
        # Skip if this content is completed
        display_name = file_manager.format_display_name(audio_file)
        if display_name in completed_names:
            continue
        
        # Check for corresponding transcript and PDF
        transcript_path = Config.TRANSCRIPTS_DIR / f"{base_name}_transcript.txt"
        pdf_path = Config.PDF_DIR / f"{base_name}_transcript.pdf"
        
        if transcript_path.exists():
            content_list.append({
                'name': base_name,
                'audio': str(audio_file),
                'transcript': str(transcript_path) if transcript_path.exists() else None,
                'pdf': str(pdf_path) if pdf_path.exists() else None
            })
    
    return content_list

def load_content_for_reading(content_name: str):
    """Load audio and transcript text for a selected content"""
    try:
        if not content_name:
            return None, "<p style='text-align: center; padding: 50px; color: #666;'>Please select content to view</p>", "Please select content to view"

        content_list = get_available_content()
        selected = next((c for c in content_list if c['name'] == content_name), None)

        if not selected:
            return None, "<p style='text-align: center; padding: 50px; color: #666;'>Content not found</p>", "Content not found"
        
        # Track that this content was accessed
        history_manager.mark_as_accessed(content_name)
        
        # Check if transcript exists
        transcript_html = ""
        status = ""
        
        if selected['transcript'] and Path(selected['transcript']).exists():
            # Read the transcript text
            with open(selected['transcript'], 'r', encoding='utf-8') as f:
                transcript_text = f.read()
            
            # Create HTML with the transcript text in a readable format
            # Escape HTML and preserve line breaks
            import html
            escaped_text = html.escape(transcript_text)
            formatted_text = escaped_text.replace('\n', '<br>')
            
            transcript_html = f"""
            <div style="width: 100%; height: 600px; overflow-y: auto; border: 2px solid #e5e7eb; border-radius: 8px; padding: 25px; background: white; font-family: 'Georgia', serif; line-height: 1.8;">
                <div style="border-bottom: 2px solid #111827; padding-bottom: 15px; margin-bottom: 20px;">
                    <h2 style="margin: 0; color: #111827; font-size: 1.5rem;">{content_name}</h2>
                    <p style="margin: 5px 0 0 0; color: #6b7280; font-size: 0.9rem;">Transcript</p>
                </div>
                <div style="color: #374151; font-size: 1.05rem; text-align: justify;">
                    {formatted_text}
                </div>
            </div>
            """
            status = f"Ready to read: {content_name}"
        else:
            transcript_html = """
            <div style="text-align: center; padding: 50px; color: #9ca3af; border: 2px dashed #9ca3af; border-radius: 8px; background: #f3f4f6;">
                <h3 style="margin: 0 0 10px 0; color: #374151;">Transcript Not Found</h3>
                <p style="margin: 0; color: #4b5563;">Please transcribe this audio first from the "Transcribe" tab.</p>
            </div>
            """
            status = f"Transcript not found. Please transcribe this audio first."

        return selected['audio'], transcript_html, status

    except Exception as e:
        return None, f"<p style='text-align: center; padding: 50px; color: #111827;'>Error: {str(e)}</p>", f"Error: {str(e)}"

def generate_pdf_for_reader(content_name: str):
    """Generate PDF for the selected content if it doesn't exist"""
    try:
        if not content_name:
            return "<p style='text-align: center; padding: 50px; color: #666;'>Please select content first</p>", "Please select content first", None

        transcript_path = Config.TRANSCRIPTS_DIR / f"{content_name}_transcript.txt"

        if not transcript_path.exists():
            return "<p style='text-align: center; padding: 50px; color: #111827;'>Transcript not found</p>", "Transcript not found", None

        # Generate PDF
        pdf_path = pdf_generator.generate_pdf(transcript_path)

        # Create simple HTML message (compact)
        pdf_html = f"""
        <div style="width: 100%; border: 2px solid #9ca3af; border-radius: 8px; padding: 20px; background: #f3f4f6; text-align: center;">
            <h3 style="margin: 0 0 10px 0; color: #111827; font-size: 1.2rem;">{content_name}</h3>
            <p style="margin: 0 0 15px 0; color: #475569; font-size: 0.95rem;">
                PDF generated successfully!
            </p>
            <div style="background: white; border-radius: 6px; padding: 12px; margin: 10px 0; box-shadow: 0 1px 4px rgba(0,0,0,0.1);">
                <p style="margin: 0; color: #64748b; font-size: 0.85rem;">
                    Use the <strong style="color: #111827;">"Download PDF"</strong> button on the right
                </p>
            </div>
        </div>
        """

        return pdf_html, f"PDF generated successfully for: {content_name}", str(pdf_path)

    except Exception as e:
        return f"<p style='text-align: center; padding: 50px; color: #111827;'>Error: {str(e)}</p>", f"Error: {str(e)}", None



def mark_content_as_completed(content_name: str):
    """Mark content as completed"""
    try:
        if not content_name:
            return "Please select content first"

        history_manager.mark_as_completed(content_name)
        return f"Marked '{content_name}' as completed!"
    except Exception as e:
        return f"Error: {str(e)}"

# ============================================================================
# TAB 5: HISTORY
# ============================================================================

def get_listening_history_display(status_filter: str = "All"):
    """Get listening history formatted for display"""
    try:
        filter_map = {
            "All": None,
            "In Progress": "in_progress",
            "Completed": "completed"
        }
        
        records = history_manager.get_history(filter_map.get(status_filter))
        
        if not records:
            return "No history found"
        
        output = []
        for record in records:
            output.append(f"**{record['content_name']}**")
            output.append(f"   Status: {record['status'].replace('_', ' ').title()}")
            output.append(f"   Last accessed: {record.get('last_accessed', 'N/A')}")
            if record.get('completed_at'):
                output.append(f"   Completed: {record['completed_at']}")
            output.append("")

        return "\n".join(output)
    except Exception as e:
        return f"Error: {str(e)}"

def get_history_statistics():
    """Get history statistics"""
    try:
        stats = history_manager.get_statistics()
        return f"""**Listening Statistics**

Completed: {stats['completed']}
Total Content: {stats['total_content']}
Completion Rate: {stats['completion_rate']}%
"""
    except Exception as e:
        return f"Error: {str(e)}"

# ============================================================================
# GRADIO INTERFACE
# ============================================================================

# Custom CSS for a monochrome, grayscale design
custom_css = """
/* Grayscale design system */
:root {
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-700: #374151;
    --gray-800: #1f2937;
    --gray-900: #111827;
}



/* Header styling */
.gradio-container h1 {
    color: #111827 !important;
    font-weight: 800;
    font-size: 2.5rem !important;
    margin-bottom: 0.5rem !important;
}

/* Tab styling */
.tab-nav button {
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    padding: 0.75rem 1.5rem !important;
    border-radius: 0.5rem !important;
    transition: all 0.2s ease !important;
}

.tab-nav button[aria-selected="true"] {
    background: #111827 !important;
    color: white !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
}

.tab-nav button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
}

/* Button improvements */
.primary {
    background: #111827 !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.5rem !important;
    border-radius: 0.5rem !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
    transition: all 0.2s ease !important;
}

.primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3) !important;
}

.secondary {
    background: #6b7280 !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 0.5rem !important;
}

/* Card-like containers */
.gr-box {
    border-radius: 1rem !important;
    border: 1px solid #e5e7eb !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1) !important;
    transition: all 0.2s ease !important;
}

.gr-box:hover {
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1) !important;
}

/* Input fields */
input, textarea, select {
    border-radius: 0.5rem !important;
    border: 2px solid #e5e7eb !important;
    transition: all 0.2s ease !important;
}

input:focus, textarea:focus, select:focus {
    border-color: #111827 !important;
    box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.1) !important;
}

/* Dropdown styling */
.gr-dropdown {
    border-radius: 0.5rem !important;
}

/* Status messages */
.gr-textbox:has(> label:contains("Status")) {
    font-weight: 500;
}

.message-wrap {
    border-radius: 1rem !important;
    padding: 1rem !important;
    margin: 0.5rem 0 !important;
}

.message.user {
    background: #111827 !important;
    color: white !important;
}

.message.bot {
    background: #f3f4f6 !important;
    border: 1px solid #e5e7eb !important;
}

/* Audio player */
audio {
    border-radius: 0.75rem !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
}

/* File upload area */
.upload-container {
    border: 2px dashed #d1d5db !important;
    border-radius: 1rem !important;
    transition: all 0.2s ease !important;
}

.upload-container:hover {
    border-color: #111827 !important;
    background: #f3f4f6 !important;
}

/* Markdown content */
.prose {
    line-height: 1.7 !important;
}

.prose h2 {
    color: #1f2937 !important;
    font-weight: 700 !important;
    margin-top: 1.5rem !important;
}

.prose h3 {
    color: #374151 !important;
    font-weight: 600 !important;
}

/* Loading states */
.loading {
    background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 50%, #f3f4f6 75%);
    background-size: 200% 100%;
    animation: loading 1.5s ease-in-out infinite;
}

@keyframes loading {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* Scrollbar styling */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: #f3f4f6;
    border-radius: 4px;
}

::-webkit-scrollbar-thumb {
    background: #111827;
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: #374151;
}

/* Responsive improvements */
@media (max-width: 100%) {
    .gradio-container h1 {
        font-size: 1.75rem !important;
    }

    .tab-nav button {
        padding: 0.5rem 1rem !important;
        font-size: 0.875rem !important;
    }
}
"""

# Custom theme - grayscale, monochrome
custom_theme = gr.themes.Soft(
    primary_hue="gray",
    secondary_hue="gray",
    neutral_hue="gray",
).set(
    body_background_fill="#f9fafb",
    button_primary_background_fill="#111827",
    button_primary_background_fill_hover="#1f2937",
    button_primary_text_color="white",
    button_secondary_background_fill="#6b7280",
    button_secondary_text_color="white",
    input_border_color="#e5e7eb",
    input_border_width="2px",
    block_border_width="1px",
    block_shadow="0 1px 3px 0 rgba(0, 0, 0, 0.1)",
)

with gr.Blocks(
    title="BBC Audio Transcript - Alex Snow School",
    theme=custom_theme,
    css=custom_css,

) as app:

    gr.Markdown("# BBC Audio Transcript")
    gr.Markdown("Download · Transcribe — Powered by Whisper AI — [Alex Snow School](https://alexsnowschool.org/)")

    with gr.Tabs():
        # ====================================================================
        # TAB 1: DOWNLOAD
        # ====================================================================
        with gr.Tab("Download Audio"):

            # RSS Feed Download Section
            gr.HTML("""
            <div style='margin-bottom: 1rem;'>
                <h3 style='color: #374151; font-weight: 600; margin-bottom: 0.5rem;'>RSS Feed Download</h3>
                <p style='color: #6b7280; font-size: 0.9rem; margin: 0;'>Enter an RSS feed URL to download audio content</p>
            </div>
            """)
            
            with gr.Row():
                with gr.Column(scale=3):
                    rss_url = gr.Textbox(
                        label="RSS Feed URL",
                        placeholder="https://podcasts.files.bbci.co.uk/p00fzl9g.rss",
                        lines=1,
                        info="Paste the RSS feed URL from BBC Sounds or other podcast sources"
                    )
                with gr.Column(scale=1):
                    rss_limit = gr.Number(
                        label="Max Episodes", 
                        value=5, 
                        precision=0,
                        info="Number of episodes to download"
                    )
            
            with gr.Row():
                rss_btn = gr.Button("Download from RSS", variant="primary", size="lg")
                feeds_btn = gr.Button("Show Popular Feeds", variant="secondary")

            # Download Status Section
            gr.HTML("""
            <div style='margin: 1.5rem 0 0.5rem 0;'>
                <h3 style='color: #374151; font-weight: 600; margin-bottom: 0.5rem;'>Download Status</h3>
            </div>
            """)
            download_output = gr.Textbox(
                label="Status & Output", 
                lines=8,
                placeholder="Download status will appear here...",
                show_label=False
            )
            
            gr.Markdown("---")
            
            # Downloaded Files Section
            gr.HTML("""
            <div style='margin-bottom: 0.5rem;'>
                <h3 style='color: #374151; font-weight: 600; margin-bottom: 0.5rem;'>Downloaded Files</h3>
                <p style='color: #6b7280; font-size: 0.9rem; margin: 0;'>View and manage your downloaded audio files</p>
            </div>
            """)

            refresh_downloads_btn = gr.Button("Refresh File List", size="sm")
            downloads_list = gr.Textbox(
                label="Available Audio Files", 
                lines=6,
                placeholder="Click 'Refresh File List' to see downloaded files...",
                show_label=False
            )
            
            # Event handlers
            rss_btn.click(download_from_rss, [rss_url, rss_limit], download_output)
            feeds_btn.click(get_popular_feeds, None, download_output)
            refresh_downloads_btn.click(list_downloads, None, downloads_list)
                
            # Quick Start Guide
            gr.Markdown("---")
            gr.HTML("""
            <div style='background: #ffffff; padding: 1.5rem; border-radius: 1rem; border: 2px solid #e5e7eb; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>
                <h3 style='color: #1f2937; margin: 0 0 1rem 0; font-weight: 700; font-size: 1.3rem;'>Quick Start Guide</h3>

                <div style='display: grid; gap: 1rem;'>
                    <div style='background: #f3f4f6; padding: 1.25rem; border-radius: 0.75rem; border-left: 4px solid #6b7280;'>
                        <div style='font-weight: 700; color: #111827; margin-bottom: 0.5rem; font-size: 1.05rem;'>Step 1: Download</div>
                        <div style='color: #1f2937; font-size: 0.95rem; line-height: 1.6;'>
                            Use the RSS feed URL for Reith Lectures:<br>
                            <code style='background: #ffffff; padding: 0.4rem 0.6rem; border-radius: 0.375rem; font-size: 0.85rem; color: #1f2937; border: 1px solid #d1d5db; display: inline-block; margin-top: 0.25rem;'>https://podcasts.files.bbci.co.uk/p02p8xh7.rss</code>
                        </div>
                    </div>

                    <div style='background: #f3f4f6; padding: 1.25rem; border-radius: 0.75rem; border-left: 4px solid #374151;'>
                        <div style='font-weight: 700; color: #111827; margin-bottom: 0.5rem; font-size: 1.05rem;'>Step 2: Transcribe</div>
                        <div style='color: #1f2937; font-size: 0.95rem; line-height: 1.6;'>
                            Go to the <strong style='color: #1f2937;'>Transcribe</strong> tab, select your downloaded audio, and click "Transcribe" (powered by Whisper AI)
                        </div>
                    </div>
                </div>
            </div>
            """)
        
        # ====================================================================
        # TAB 2: TRANSCRIBE
        # ====================================================================
        with gr.Tab("Transcribe"):
            gr.Markdown("### Transcribe Audio to Text")

            # Topic Filter Buttons
            gr.Markdown("### Filter by Topic")
            gr.Markdown("Browse audio files by subject area")

            # Create topic filter buttons
            topic_buttons = []
            topic_btn_refs = []  # List of just buttons for the update function

            with gr.Row():
                # Refresh button
                refresh_topics_btn = gr.Button("Refresh Topics", size="sm", variant="secondary")

                # Add "All Topics" button
                all_topics_btn = gr.Button("All Topics", variant="secondary", size="sm")
                topic_buttons.append(("All Topics", all_topics_btn))
                topic_btn_refs.append(all_topics_btn)
            
            # Status indicator for refresh
            refresh_topics_status = gr.Textbox(
                label="",
                show_label=False,
                lines=1,
                max_lines=1,
                interactive=False,
                visible=True,
                placeholder="Click 'Refresh Topics' to update topic counts"
            )
            
            # Create a row of buttons for all predefined topics
            
            with gr.Row():
                all_topics_data = topic_categorizer.get_all_topics()
                topic_counts = {t['topic']: t['count'] for t in all_topics_data}
                
                for topic in topic_categorizer.PREDEFINED_TOPICS:
                    count = topic_counts.get(topic, 0)
                    btn = gr.Button(f"{topic} ({count})", variant="secondary", size="sm")
                    topic_buttons.append((topic, btn))
                    topic_btn_refs.append(btn)

            def show_loading():
                """Show loading message"""
                return "Refreshing topics..."
            
            def refresh_topics_ui():
                """Refreshes topic categorization and updates button labels"""
                # 1. Categorize any new files (this handles cache and API calls)
                topic_categorizer.categorize_all_files(file_manager.list_audio_files())
                
                # 2. Get updated stats
                all_topics_data = topic_categorizer.get_all_topics()
                topic_counts = {t['topic']: t['count'] for t in all_topics_data}
                
                # 3. Prepare updates
                updates = []
                
                # First update is for "All Topics" button (no change needed usually, but good to keep synced)
                updates.append(gr.update())
                
                # Updates for each topic button
                for topic in topic_categorizer.PREDEFINED_TOPICS:
                    count = topic_counts.get(topic, 0)
                    new_label = f"{topic} ({count})"
                    updates.append(gr.update(value=new_label))

                # Add success status message
                status_message = "Topics refreshed successfully!"
                updates.append(status_message)
                    
                return updates

            # Connect refresh button with loading indicator
            refresh_topics_btn.click(
                show_loading,
                None,
                refresh_topics_status
            ).then(
                refresh_topics_ui,
                None,
                topic_btn_refs + [refresh_topics_status]
            )
            
            gr.Markdown("---")
            
            with gr.Row():
                with gr.Column():
                    audio_file = gr.Dropdown(
                        label="Select Audio File",
                        choices=[
                            (file_manager.format_display_name(f), str(f)) 
                            for f in file_manager.list_audio_files_sorted_by_date()
                            if file_manager.format_display_name(f) not in history_manager.get_completed_content_names()
                        ],
                        interactive=True
                    )
                    refresh_audio_btn = gr.Button("Refresh Audio List")
                    
                    model_size = gr.Dropdown(
                        label="Whisper Model Size",
                        choices=["tiny", "base", "small", "medium", "large"],
                        value="base",
                        info="Larger = more accurate but slower"
                    )
                    language = gr.Textbox(
                        label="Language Code", 
                        value="english",
                        info="Use 'english', 'spanish', 'french', etc."
                    )
                    
                    transcribe_btn = gr.Button("Transcribe Selected File", variant="primary")
                
                with gr.Column():
                    transcribe_output = gr.Textbox(label="Status", lines=10)

            
            # Event handlers
            refresh_audio_btn.click(
                lambda: gr.Dropdown(choices=[
                    (file_manager.format_display_name(f), str(f)) 
                    for f in file_manager.list_audio_files_sorted_by_date()
                    if file_manager.format_display_name(f) not in history_manager.get_completed_content_names()
                ]),
                None,
                audio_file
            )
            transcribe_btn.click(
                transcribe_file,
                [audio_file, model_size, language],
                transcribe_output
            )
            
            gr.Markdown("---")
            gr.Markdown("#### Export to PDF")
            gr.Markdown("Generate formatted PDF documents from your transcripts for offline reading")
            
            with gr.Row():
                with gr.Column():
                    transcript_selector = gr.Dropdown(
                        label="Select Transcript to Export",
                        choices=[
                            t.name for t in file_manager.list_transcripts()
                            if file_manager.format_display_name(t) not in history_manager.get_completed_content_names()
                        ],
                        interactive=True
                    )
                    refresh_pdf_list_btn = gr.Button("Refresh Transcript List")
                    
                    with gr.Row():
                        export_single_btn = gr.Button("Export Selected to PDF", variant="primary")
                        export_all_btn = gr.Button("Export All to PDF")
                
                with gr.Column():
                    pdf_output = gr.Textbox(label="Export Status", lines=3)
                    pdf_file = gr.File(label="Download PDF", visible=True)
            
            # PDF Export Event handlers
            refresh_pdf_list_btn.click(
                lambda: gr.Dropdown(choices=[
                    t.name for t in file_manager.list_transcripts()
                    if file_manager.format_display_name(t) not in history_manager.get_completed_content_names()
                ]),
                None,
                transcript_selector
            )
            export_single_btn.click(
                export_transcript_to_pdf,
                transcript_selector,
                [pdf_output, pdf_file]
            )
            export_all_btn.click(
                export_all_transcripts_to_pdf,
                None,
                pdf_output
            )
            
            # Topic filter event handlers
            def filter_audio_by_topic(topic):
                """Filter audio files by selected topic"""
                if topic == "All Topics":
                    files = file_manager.list_audio_files_sorted_by_date()
                else:
                    files = topic_categorizer.get_files_by_topic(topic)
                
                # Filter out completed files
                completed_names = history_manager.get_completed_content_names()
                choices = [
                    (file_manager.format_display_name(f), str(f))
                    for f in files
                    if file_manager.format_display_name(f) not in completed_names
                ]
                
                # Auto-select first item if available
                selected_value = choices[0][1] if choices else None
                
                return gr.Dropdown(choices=choices, value=selected_value)
            
            # Connect topic buttons to filter function
            for topic, btn in topic_buttons:
                btn.click(
                    lambda t=topic: filter_audio_by_topic(t),
                    None,
                    audio_file
                )

        
        # ====================================================================
        # Read & Listen Tab - Text Transcript with Audio
        # ====================================================================
        with gr.Tab("Read & Listen"):
            gr.Markdown("""
            ### Read & Listen to Transcripts
            Listen to audio while reading the transcript text. Perfect for focused learning!
            """)

            with gr.Row():
                content_selector = gr.Dropdown(
                    label="Select Content",
                    choices=[],
                    interactive=True
                )
                refresh_content_btn = gr.Button("Refresh List", size="sm")

            load_content_btn = gr.Button("Load Content", variant="primary")
            mark_completed_btn = gr.Button("Mark as Completed", variant="secondary")

            reader_status = gr.Textbox(label="Status", lines=2)

            gr.Markdown("---")

            gr.Markdown("---")
            # Audio player at the top - compact
            gr.Markdown("#### Audio Player")
            audio_player = gr.Audio(
                label="",
                type="filepath",
                interactive=False,
                show_label=False
            )

            gr.Markdown("---")

            # Transcript text viewer
            gr.Markdown("#### Transcript")
            transcript_viewer = gr.HTML(
                label="Transcript",
                value="<p style='text-align: center; padding: 50px; color: #666;'>Select content and click 'Load Content' to view transcript</p>"
            )
           
            # Event handlers for Read & Listen
            refresh_content_btn.click(
                lambda: gr.Dropdown(choices=[c['name'] for c in get_available_content()]),
                None,
                content_selector
            )
            
            load_content_btn.click(
                load_content_for_reading,
                content_selector,
                [audio_player, transcript_viewer, reader_status]
            )
            
            mark_completed_btn.click(
                mark_content_as_completed,
                content_selector,
                reader_status
            )
        
        # ====================================================================
        # TAB 5: HISTORY
        # ====================================================================
        with gr.Tab("History"):
            gr.Markdown("### View Your Listening History")
            gr.Markdown("#### Track your progress through audio content")

            history_display = gr.Markdown(value=get_listening_history_display("All"))
            refresh_history_btn = gr.Button("Refresh History")

            refresh_history_btn.click(
                lambda: get_listening_history_display("All"),
                [],
                history_display
            )

    gr.Markdown("---")
    gr.Markdown("*Made with care from [Alex Snow School](https://alexsnowschool.org/)*")


if __name__ == "__main__":
    logger.info("Starting BBC Audio Scraper application")
    app.launch(server_name="0.0.0.0", server_port=7860, share=False, favicon_path="./logo/logo.png")
