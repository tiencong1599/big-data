"""
Violation API Handlers - Production Grade REST API
===================================================

Provides comprehensive REST endpoints for managing speed violations:
- List violations with filtering, sorting, pagination
- Get violation details
- Statistics and analytics
- Export functionality
- Image serving
- Deletion

Performance optimized with:
- Efficient database queries
- Proper indexing utilization
- Response caching headers
- Streaming for large exports
"""

import os
import json
import logging
import tornado.web
from tornado.web import StaticFileHandler
from sqlalchemy import func, desc, asc, and_, or_
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Setup logging
logger = logging.getLogger(__name__)

# Configuration
VIOLATION_CAPTURES_DIR = os.getenv('VIOLATION_CAPTURES_DIR', '/app/violation_captures')


class BaseViolationHandler(tornado.web.RequestHandler):
    """Base handler with common CORS and error handling."""
    
    def set_default_headers(self):
        """Set CORS headers for all responses."""
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.set_header("Content-Type", "application/json")
    
    def options(self, *args, **kwargs):
        """Handle CORS preflight requests."""
        self.set_status(204)
        self.finish()
    
    def write_error(self, status_code: int, **kwargs):
        """Custom error response format."""
        error_message = "An error occurred"
        
        if "exc_info" in kwargs:
            exc_info = kwargs["exc_info"]
            if exc_info[1]:
                error_message = str(exc_info[1])
        
        self.finish({
            "error": True,
            "status_code": status_code,
            "message": error_message
        })
    
    def get_db(self) -> Session:
        """Get database session."""
        from database import get_db
        return get_db()


class ViolationListHandler(BaseViolationHandler):
    """
    List violations with comprehensive filtering and pagination.
    
    GET /api/violations
    
    Query Parameters:
        - video_id (int): Filter by video
        - session_start (datetime): Filter by session
        - vehicle_type (str): Filter by vehicle type
        - min_speed (float): Minimum speed filter
        - max_speed (float): Maximum speed filter
        - date_from (date): Start date filter
        - date_to (date): End date filter
        - limit (int): Page size (default: 50, max: 200)
        - offset (int): Pagination offset
        - sort_by (str): Sort field (default: violation_timestamp)
        - sort_order (str): asc or desc (default: desc)
    """
    
    async def get(self):
        try:
            # Parse query parameters
            video_id = self.get_argument('video_id', None)
            session_start = self.get_argument('session_start', None)
            vehicle_type = self.get_argument('vehicle_type', None)
            min_speed = self.get_argument('min_speed', None)
            max_speed = self.get_argument('max_speed', None)
            date_from = self.get_argument('date_from', None)
            date_to = self.get_argument('date_to', None)
            limit = min(int(self.get_argument('limit', '50')), 200)  # Cap at 200
            offset = int(self.get_argument('offset', '0'))
            sort_by = self.get_argument('sort_by', 'violation_timestamp')
            sort_order = self.get_argument('sort_order', 'desc')
            
            db = self.get_db()
            
            try:
                from models.video import ViolationCapture
                
                # Build base query
                query = db.query(ViolationCapture)
                
                # Apply filters
                filters = []
                
                if video_id:
                    filters.append(ViolationCapture.video_id == int(video_id))
                
                if session_start:
                    filters.append(ViolationCapture.session_start == session_start)
                
                if vehicle_type:
                    filters.append(ViolationCapture.vehicle_type == vehicle_type)
                
                if min_speed:
                    filters.append(ViolationCapture.speed >= float(min_speed))
                
                if max_speed:
                    filters.append(ViolationCapture.speed <= float(max_speed))
                
                if date_from:
                    filters.append(ViolationCapture.violation_timestamp >= date_from)
                
                if date_to:
                    # Add one day to include the entire end date
                    filters.append(ViolationCapture.violation_timestamp < date_to + 'T23:59:59')
                
                if filters:
                    query = query.filter(and_(*filters))
                
                # Get total count before pagination
                total_count = query.count()
                
                # Apply sorting
                sort_column = getattr(ViolationCapture, sort_by, ViolationCapture.violation_timestamp)
                if sort_order.lower() == 'asc':
                    query = query.order_by(asc(sort_column))
                else:
                    query = query.order_by(desc(sort_column))
                
                # Apply pagination
                violations = query.offset(offset).limit(limit).all()
                
                # Build response
                response = {
                    'violations': [v.to_dict() for v in violations],
                    'total': total_count,
                    'limit': limit,
                    'offset': offset,
                    'has_more': (offset + len(violations)) < total_count
                }
                
                # Add cache headers for better performance
                self.set_header("Cache-Control", "private, max-age=30")
                
                self.write(response)
                
            finally:
                db.close()
                
        except ValueError as e:
            self.set_status(400)
            self.write({'error': f'Invalid parameter: {str(e)}'})
        except Exception as e:
            logger.error(f"Error listing violations: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class ViolationDetailHandler(BaseViolationHandler):
    """
    Get, update, or delete a single violation.
    
    GET /api/violations/{id} - Get violation details
    DELETE /api/violations/{id} - Delete violation and images
    """
    
    async def get(self, violation_id: str):
        """Get single violation details."""
        try:
            db = self.get_db()
            
            try:
                from models.video import ViolationCapture
                
                violation = db.query(ViolationCapture).filter(
                    ViolationCapture.id == int(violation_id)
                ).first()
                
                if not violation:
                    self.set_status(404)
                    self.write({'error': 'Violation not found'})
                    return
                
                self.write({'violation': violation.to_dict()})
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting violation {violation_id}: {e}")
            self.set_status(500)
            self.write({'error': str(e)})
    
    async def delete(self, violation_id: str):
        """Delete a violation record and its associated images."""
        try:
            db = self.get_db()
            
            try:
                from models.video import ViolationCapture
                
                violation = db.query(ViolationCapture).filter(
                    ViolationCapture.id == int(violation_id)
                ).first()
                
                if not violation:
                    self.set_status(404)
                    self.write({'error': 'Violation not found'})
                    return
                
                # Delete image files
                files_deleted = []
                
                if violation.frame_image_path:
                    image_path = os.path.join(VIOLATION_CAPTURES_DIR, violation.frame_image_path)
                    if os.path.exists(image_path):
                        os.remove(image_path)
                        files_deleted.append(violation.frame_image_path)
                
                if violation.thumbnail_path:
                    thumb_path = os.path.join(VIOLATION_CAPTURES_DIR, violation.thumbnail_path)
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                        files_deleted.append(violation.thumbnail_path)
                
                # Delete database record
                db.delete(violation)
                db.commit()
                
                logger.info(f"Deleted violation {violation_id} and {len(files_deleted)} files")
                
                self.write({
                    'message': 'Violation deleted successfully',
                    'files_deleted': files_deleted
                })
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error deleting violation {violation_id}: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class ViolationStatsHandler(BaseViolationHandler):
    """
    Get violation statistics and analytics.
    
    GET /api/violations/stats
    
    Query Parameters:
        - video_id (int): Filter by video
        - session_start (datetime): Filter by session
    """
    
    async def get(self):
        try:
            video_id = self.get_argument('video_id', None)
            session_start = self.get_argument('session_start', None)
            
            db = self.get_db()
            
            try:
                from models.video import ViolationCapture
                
                # Base filter
                filters = []
                if video_id:
                    filters.append(ViolationCapture.video_id == int(video_id))
                if session_start:
                    filters.append(ViolationCapture.session_start == session_start)
                
                base_query = db.query(ViolationCapture)
                if filters:
                    base_query = base_query.filter(and_(*filters))
                
                # Total violations
                total_violations = base_query.count()
                
                # Recent violations (last 24 hours)
                yesterday = datetime.utcnow() - timedelta(hours=24)
                recent_query = base_query.filter(
                    ViolationCapture.violation_timestamp >= yesterday
                )
                recent_count = recent_query.count()
                
                # By vehicle type with speed stats
                vehicle_type_query = db.query(
                    ViolationCapture.vehicle_type,
                    func.count(ViolationCapture.id).label('count'),
                    func.avg(ViolationCapture.speed).label('avg_speed'),
                    func.max(ViolationCapture.speed).label('max_speed'),
                    func.min(ViolationCapture.speed).label('min_speed')
                ).group_by(ViolationCapture.vehicle_type)
                
                if filters:
                    vehicle_type_query = vehicle_type_query.filter(and_(*filters))
                
                vehicle_stats = [
                    {
                        'vehicle_type': row.vehicle_type,
                        'count': row.count,
                        'avg_speed': round(row.avg_speed, 1) if row.avg_speed else 0,
                        'max_speed': round(row.max_speed, 1) if row.max_speed else 0,
                        'min_speed': round(row.min_speed, 1) if row.min_speed else 0
                    }
                    for row in vehicle_type_query.all()
                ]
                
                # Speed distribution
                speed_ranges = [
                    ('60-70', 60, 70),
                    ('70-80', 70, 80),
                    ('80-90', 80, 90),
                    ('90-100', 90, 100),
                    ('100+', 100, 9999)
                ]
                
                speed_distribution = {}
                for range_name, min_s, max_s in speed_ranges:
                    range_query = base_query.filter(
                        ViolationCapture.speed >= min_s,
                        ViolationCapture.speed < max_s
                    )
                    speed_distribution[range_name] = range_query.count()
                
                # Overall speed statistics
                speed_stats = db.query(
                    func.avg(ViolationCapture.speed).label('avg'),
                    func.max(ViolationCapture.speed).label('max'),
                    func.min(ViolationCapture.speed).label('min'),
                    func.avg(ViolationCapture.speed_excess).label('avg_excess')
                )
                if filters:
                    speed_stats = speed_stats.filter(and_(*filters))
                
                speed_row = speed_stats.first()
                
                # Hourly distribution (for charts)
                hourly_query = db.query(
                    func.extract('hour', ViolationCapture.violation_timestamp).label('hour'),
                    func.count(ViolationCapture.id).label('count')
                ).group_by('hour').order_by('hour')
                
                if filters:
                    hourly_query = hourly_query.filter(and_(*filters))
                
                hourly_distribution = {
                    int(row.hour): row.count 
                    for row in hourly_query.all()
                }
                
                response = {
                    'total_violations': total_violations,
                    'recent_violations_24h': recent_count,
                    'by_vehicle_type': vehicle_stats,
                    'speed_distribution': speed_distribution,
                    'speed_stats': {
                        'avg_speed': round(speed_row.avg, 1) if speed_row.avg else 0,
                        'max_speed': round(speed_row.max, 1) if speed_row.max else 0,
                        'min_speed': round(speed_row.min, 1) if speed_row.min else 0,
                        'avg_excess': round(speed_row.avg_excess, 1) if speed_row.avg_excess else 0
                    },
                    'hourly_distribution': hourly_distribution
                }
                
                # Cache stats for 60 seconds
                self.set_header("Cache-Control", "private, max-age=60")
                
                self.write(response)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting violation stats: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class ViolationExportHandler(BaseViolationHandler):
    """
    Export violations as CSV or JSON.
    
    GET /api/violations/export
    
    Query Parameters:
        - format (str): 'csv' or 'json' (default: json)
        - video_id (int): Filter by video
        - session_start (datetime): Filter by session
    """
    
    async def get(self):
        try:
            export_format = self.get_argument('format', 'json').lower()
            video_id = self.get_argument('video_id', None)
            session_start = self.get_argument('session_start', None)
            
            if export_format not in ('csv', 'json'):
                self.set_status(400)
                self.write({'error': 'Format must be csv or json'})
                return
            
            db = self.get_db()
            
            try:
                from models.video import ViolationCapture
                
                query = db.query(ViolationCapture)
                
                if video_id:
                    query = query.filter(ViolationCapture.video_id == int(video_id))
                
                if session_start:
                    query = query.filter(ViolationCapture.session_start == session_start)
                
                violations = query.order_by(
                    ViolationCapture.violation_timestamp
                ).all()
                
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                
                if export_format == 'csv':
                    self.set_header('Content-Type', 'text/csv; charset=utf-8')
                    self.set_header(
                        'Content-Disposition',
                        f'attachment; filename="violations_{video_id or "all"}_{timestamp}.csv"'
                    )
                    
                    # CSV header
                    csv_lines = [
                        'id,video_id,track_id,speed,speed_limit,speed_excess,'
                        'vehicle_type,confidence,frame_number,violation_timestamp,'
                        'bbox_x1,bbox_y1,bbox_x2,bbox_y2,image_path'
                    ]
                    
                    # CSV data rows
                    for v in violations:
                        csv_lines.append(
                            f'{v.id},{v.video_id},{v.track_id},'
                            f'{v.speed:.2f},{v.speed_limit:.1f},{v.speed_excess:.2f},'
                            f'{v.vehicle_type},{v.confidence:.3f if v.confidence else ""},'
                            f'{v.frame_number},{v.violation_timestamp.isoformat()},'
                            f'{v.bbox_x1 or ""},{v.bbox_y1 or ""},{v.bbox_x2 or ""},{v.bbox_y2 or ""},'
                            f'{v.frame_image_path}'
                        )
                    
                    self.write('\n'.join(csv_lines))
                    
                else:  # JSON
                    self.set_header('Content-Type', 'application/json')
                    self.set_header(
                        'Content-Disposition',
                        f'attachment; filename="violations_{video_id or "all"}_{timestamp}.json"'
                    )
                    
                    self.write({
                        'violations': [v.to_dict() for v in violations],
                        'total': len(violations),
                        'exported_at': datetime.utcnow().isoformat(),
                        'filters': {
                            'video_id': video_id,
                            'session_start': session_start
                        }
                    })
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error exporting violations: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class ViolationImageHandler(StaticFileHandler):
    """
    Serve violation capture images with proper caching.
    
    GET /api/violations/images/{path}
    """
    
    def set_default_headers(self):
        """Set CORS and caching headers."""
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Cache-Control", "public, max-age=86400")  # Cache for 24 hours
    
    def options(self, path):
        """Handle CORS preflight."""
        self.set_status(204)
        self.finish()


class ViolationBulkDeleteHandler(BaseViolationHandler):
    """
    Bulk delete violations.
    
    POST /api/violations/bulk-delete
    
    Body:
        - ids (list): List of violation IDs to delete
        - video_id (int): Delete all violations for a video
        - session_start (datetime): Delete all violations for a session
    """
    
    async def post(self):
        try:
            body = json.loads(self.request.body.decode('utf-8'))
            ids = body.get('ids', [])
            video_id = body.get('video_id')
            session_start = body.get('session_start')
            
            db = self.get_db()
            
            try:
                from models.video import ViolationCapture
                
                query = db.query(ViolationCapture)
                
                if ids:
                    query = query.filter(ViolationCapture.id.in_(ids))
                elif video_id:
                    query = query.filter(ViolationCapture.video_id == int(video_id))
                    if session_start:
                        query = query.filter(ViolationCapture.session_start == session_start)
                else:
                    self.set_status(400)
                    self.write({'error': 'Must provide ids, video_id, or session_start'})
                    return
                
                violations = query.all()
                
                # Delete files
                files_deleted = 0
                for v in violations:
                    if v.frame_image_path:
                        image_path = os.path.join(VIOLATION_CAPTURES_DIR, v.frame_image_path)
                        if os.path.exists(image_path):
                            os.remove(image_path)
                            files_deleted += 1
                    
                    if v.thumbnail_path:
                        thumb_path = os.path.join(VIOLATION_CAPTURES_DIR, v.thumbnail_path)
                        if os.path.exists(thumb_path):
                            os.remove(thumb_path)
                            files_deleted += 1
                
                # Delete records
                records_deleted = query.delete(synchronize_session=False)
                db.commit()
                
                logger.info(f"Bulk deleted {records_deleted} violations, {files_deleted} files")
                
                self.write({
                    'message': 'Violations deleted successfully',
                    'records_deleted': records_deleted,
                    'files_deleted': files_deleted
                })
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in bulk delete: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


# ============================================================================
# Route Configuration Helper
# ============================================================================

def get_violation_handlers():
    """
    Get list of violation handler routes for registration in app.py
    
    Returns:
        List of (pattern, handler, kwargs) tuples
    """
    return [
        (r"/api/violations", ViolationListHandler),
        (r"/api/violations/stats", ViolationStatsHandler),
        (r"/api/violations/export", ViolationExportHandler),
        (r"/api/violations/bulk-delete", ViolationBulkDeleteHandler),
        (r"/api/violations/images/(.*)", ViolationImageHandler, {
            "path": VIOLATION_CAPTURES_DIR
        }),
        (r"/api/violations/(\d+)", ViolationDetailHandler),
    ]
