import tornado.web
import tornado.httpserver
import tornado.ioloop
import tornado.options
from tornado.options import define, options
import logging
import sys
from handlers.websocket_routing import get_websocket_handlers
from handlers.video_handler import VideoUploadHandler, VideoListHandler, VideoDetailHandler
from handlers.stream_handler import StreamHandler
from handlers.producer_handler import ProducerHandler
from handlers.video_stream_handler import VideoStreamHandler
from models.video import init_db
from config.settings import SERVER_PORT, ALLOWED_ORIGINS

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detail
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

define("port", default=SERVER_PORT, help="run on the given port", type=int)

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            # Video APIs
            (r"/api/videos/upload", VideoUploadHandler),
            (r"/api/videos", VideoListHandler),
            (r"/api/videos/(\d+)", VideoDetailHandler),
            
            # Streaming
            (r"/api/stream/start", StreamHandler),
            (r"/api/producer/stream", ProducerHandler),
            
            # MJPEG Video Stream (Full CSR)
            (r"/api/video/stream/(\d+)", VideoStreamHandler),
            
            # WebSocket handlers (new routing system)
            *get_websocket_handlers(),
        ]
        
        settings = {
            "debug": True,
            "autoreload": True,
        }
        
        logger.info("Initializing application with handlers:")
        for handler in handlers:
            logger.info(f"  {handler[0]} -> {handler[1].__name__}")
        
        super(Application, self).__init__(handlers, **settings)
    
    def log_request(self, handler):
        """Log every request that comes in"""
        if handler.get_status() < 400:
            log_method = logger.info
        elif handler.get_status() < 500:
            log_method = logger.warning
        else:
            log_method = logger.error
        
        request_time = 1000.0 * handler.request.request_time()
        log_method(f"{handler.request.method} {handler.request.uri} -> {handler.get_status()} ({request_time:.2f}ms)")

def main():
    # Initialize database
    logger.info("=" * 60)
    logger.info("VIDEO STREAMING BACKEND - STARTING")
    logger.info("=" * 60)
    
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")
    
    tornado.options.parse_command_line()
    app = Application()
    
    # Configure HTTP server with larger body size limit (500MB for video uploads)
    http_server = tornado.httpserver.HTTPServer(
        app,
        max_buffer_size=524288000,  # 500MB buffer size
        max_body_size=524288000,    # 500MB max body size
        idle_connection_timeout=180, # 3 minute idle timeout for long-running requests
        body_timeout=180             # 3 minute timeout for reading request body
    )
    http_server.listen(options.port)
    
    logger.info("=" * 60)
    logger.info(f"Server started successfully!")
    logger.info(f"Listening on: http://0.0.0.0:{options.port}")
    logger.info(f"API Base URL: http://localhost:{options.port}/api")
    logger.info(f"Allowed origins: {ALLOWED_ORIGINS}")
    logger.info("=" * 60)
    logger.info("Ready to accept requests...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
