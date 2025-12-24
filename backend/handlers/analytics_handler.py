"""
Analytics API handlers for querying historical analytics data
Optimized with single aggregated endpoint and caching
"""
import tornado.web
import json
import logging
from datetime import datetime
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from models.video import Video, VideoAnalyticsSnapshot, SpeedingVehicle, VideoAnalyticsSummary
from database import get_db

logger = logging.getLogger(__name__)


class AnalyticsAggregateHandler(tornado.web.RequestHandler):
    """
    Aggregated analytics endpoint - single query for all data
    GET /api/analytics/aggregate?video_id=1&include=summary,snapshots,speeding&limit=100
    """
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
    
    def options(self):
        self.set_status(204)
        self.finish()
    
    async def get(self):
        try:
            video_id = self.get_argument('video_id', None)
            includes = self.get_argument('include', 'summary').split(',')
            session_start = self.get_argument('session_start', None)
            limit = int(self.get_argument('limit', '100'))
            
            if not video_id:
                self.set_status(400)
                self.write({'error': 'video_id is required'})
                return
            
            db = get_db()
            result = {}
            
            try:
                # Summary data
                if 'summary' in includes:
                    summary_query = db.query(VideoAnalyticsSummary).filter(
                        VideoAnalyticsSummary.video_id == int(video_id)
                    )
                    if session_start:
                        summary_query = summary_query.filter(
                            VideoAnalyticsSummary.session_start == session_start
                        )
                    
                    summaries = summary_query.order_by(
                        VideoAnalyticsSummary.session_start.desc()
                    ).limit(limit).all()
                    
                    result['summary'] = [s.to_dict() for s in summaries]
                
                # Snapshots data
                if 'snapshots' in includes:
                    snapshot_query = db.query(VideoAnalyticsSnapshot).filter(
                        VideoAnalyticsSnapshot.video_id == int(video_id)
                    )
                    if session_start:
                        snapshot_query = snapshot_query.filter(
                            VideoAnalyticsSnapshot.session_start == session_start
                        )
                    
                    snapshots = snapshot_query.order_by(
                        VideoAnalyticsSnapshot.timestamp.desc()
                    ).limit(limit).all()
                    
                    result['snapshots'] = [s.to_dict() for s in snapshots]
                
                # Speeding vehicles data
                if 'speeding' in includes:
                    speeding_query = db.query(SpeedingVehicle).filter(
                        SpeedingVehicle.video_id == int(video_id)
                    )
                    if session_start:
                        speeding_query = speeding_query.filter(
                            SpeedingVehicle.session_start == session_start
                        )
                    
                    speeding = speeding_query.order_by(
                        SpeedingVehicle.timestamp.desc()
                    ).limit(limit).all()
                    
                    result['speeding'] = [v.to_dict() for v in speeding]
                
                # Trends data (aggregated from snapshots)
                if 'trends' in includes:
                    trends_query = db.query(
                        VideoAnalyticsSnapshot.timestamp,
                        func.avg(VideoAnalyticsSnapshot.total_vehicles).label('avg_total'),
                        func.avg(VideoAnalyticsSnapshot.speeding_count).label('avg_speeding'),
                        func.max(VideoAnalyticsSnapshot.max_speed).label('max_speed')
                    ).filter(
                        VideoAnalyticsSnapshot.video_id == int(video_id)
                    )
                    
                    if session_start:
                        trends_query = trends_query.filter(
                            VideoAnalyticsSnapshot.session_start == session_start
                        )
                    
                    trends = trends_query.group_by(
                        VideoAnalyticsSnapshot.timestamp
                    ).order_by(
                        VideoAnalyticsSnapshot.timestamp.desc()
                    ).limit(limit).all()
                    
                    result['trends'] = [
                        {
                            'timestamp': t.timestamp.isoformat() if t.timestamp else None,
                            'avg_total': float(t.avg_total) if t.avg_total else 0,
                            'avg_speeding': float(t.avg_speeding) if t.avg_speeding else 0,
                            'max_speed': float(t.max_speed) if t.max_speed else 0
                        }
                        for t in trends
                    ]
                
                self.write(result)
                
            finally:
                db.close()
                
        except ValueError as e:
            logger.error(f"Invalid parameter: {e}")
            self.set_status(400)
            self.write({'error': str(e)})
        except Exception as e:
            logger.error(f"Error in analytics aggregate: {e}")
            self.set_status(500)
            self.write({'error': 'Internal server error'})


class AnalyticsSummaryHandler(tornado.web.RequestHandler):
    """
    Get summary statistics for a video session
    GET /api/analytics/summary?video_id=1&session_start=...
    """
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
    
    def options(self):
        self.set_status(204)
        self.finish()
    
    async def get(self):
        try:
            video_id = self.get_argument('video_id')
            session_start = self.get_argument('session_start', None)
            
            db = get_db()
            
            try:
                query = db.query(VideoAnalyticsSummary).filter(
                    VideoAnalyticsSummary.video_id == int(video_id)
                )
                
                if session_start:
                    query = query.filter(
                        VideoAnalyticsSummary.session_start == session_start
                    )
                
                summaries = query.order_by(
                    VideoAnalyticsSummary.session_start.desc()
                ).all()
                
                self.write({'summaries': [s.to_dict() for s in summaries]})
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in analytics summary: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class AnalyticsSnapshotsHandler(tornado.web.RequestHandler):
    """
    Get analytics snapshots for a video session
    GET /api/analytics/snapshots?video_id=1&session_start=...&limit=100
    """
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
    
    def options(self):
        self.set_status(204)
        self.finish()
    
    async def get(self):
        try:
            video_id = self.get_argument('video_id')
            session_start = self.get_argument('session_start', None)
            limit = int(self.get_argument('limit', '100'))
            
            db = get_db()
            
            try:
                query = db.query(VideoAnalyticsSnapshot).filter(
                    VideoAnalyticsSnapshot.video_id == int(video_id)
                )
                
                if session_start:
                    query = query.filter(
                        VideoAnalyticsSnapshot.session_start == session_start
                    )
                
                snapshots = query.order_by(
                    VideoAnalyticsSnapshot.timestamp.desc()
                ).limit(limit).all()
                
                self.write({'snapshots': [s.to_dict() for s in snapshots]})
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in analytics snapshots: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class SpeedingVehiclesHandler(tornado.web.RequestHandler):
    """
    Get speeding vehicles for a video session
    GET /api/analytics/speeding?video_id=1&session_start=...&limit=100
    """
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
    
    def options(self):
        self.set_status(204)
        self.finish()
    
    async def get(self):
        try:
            video_id = self.get_argument('video_id')
            session_start = self.get_argument('session_start', None)
            limit = int(self.get_argument('limit', '100'))
            
            db = get_db()
            
            try:
                query = db.query(SpeedingVehicle).filter(
                    SpeedingVehicle.video_id == int(video_id)
                )
                
                if session_start:
                    query = query.filter(
                        SpeedingVehicle.session_start == session_start
                    )
                
                vehicles = query.order_by(
                    SpeedingVehicle.timestamp.desc()
                ).limit(limit).all()
                
                self.write({'vehicles': [v.to_dict() for v in vehicles]})
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in speeding vehicles: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class AnalyticsSessionsHandler(tornado.web.RequestHandler):
    """
    Get list of available sessions for a video
    GET /api/analytics/sessions?video_id=1
    """
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
    
    def options(self):
        self.set_status(204)
        self.finish()
    
    async def get(self):
        try:
            video_id = self.get_argument('video_id')
            
            db = get_db()
            
            try:
                sessions = db.query(
                    VideoAnalyticsSummary.session_start,
                    VideoAnalyticsSummary.session_end,
                    VideoAnalyticsSummary.total_vehicles_detected,
                    VideoAnalyticsSummary.total_speeding_violations
                ).filter(
                    VideoAnalyticsSummary.video_id == int(video_id)
                ).order_by(
                    VideoAnalyticsSummary.session_start.desc()
                ).all()
                
                self.write({
                    'sessions': [
                        {
                            'session_start': session_start.isoformat() if session_start else None,
                            'session_end': session_end.isoformat() if session_end else None,
                            'total_vehicles': total_vehicles,
                            'speeding_violations': speeding_violations
                        }
                        for session_start, session_end, total_vehicles, speeding_violations in sessions
                    ]
                })
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in analytics sessions: {e}")
            self.set_status(500)
            self.write({'error': str(e)})


class AnalyticsExportHandler(tornado.web.RequestHandler):
    """
    Export analytics data as CSV or JSON
    GET /api/analytics/export?video_id=1&format=csv&type=speeding
    """
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
    
    def options(self):
        self.set_status(204)
        self.finish()
    
    async def get(self):
        try:
            video_id = self.get_argument('video_id')
            export_format = self.get_argument('format', 'json')
            export_type = self.get_argument('type', 'speeding')
            session_start = self.get_argument('session_start', None)
            
            db = get_db()
            
            try:
                if export_type == 'speeding':
                    query = db.query(SpeedingVehicle).filter(
                        SpeedingVehicle.video_id == int(video_id)
                    )
                    if session_start:
                        query = query.filter(
                            SpeedingVehicle.session_start == session_start
                        )
                    
                    vehicles = query.order_by(SpeedingVehicle.timestamp).all()
                    data = [v.to_dict() for v in vehicles]
                    
                    if export_format == 'csv':
                        self.set_header('Content-Type', 'text/csv')
                        self.set_header('Content-Disposition', f'attachment; filename="speeding_vehicles_{video_id}.csv"')
                        
                        # CSV header
                        csv_lines = ['track_id,speed,class_id,timestamp,confidence\n']
                        for v in data:
                            csv_lines.append(
                                f"{v['track_id']},{v['speed']},{v['class_id']},"
                                f"{v['timestamp']},{v['confidence']}\n"
                            )
                        self.write(''.join(csv_lines))
                    else:
                        self.write({'data': data})
                
                elif export_type == 'summary':
                    query = db.query(VideoAnalyticsSummary).filter(
                        VideoAnalyticsSummary.video_id == int(video_id)
                    )
                    if session_start:
                        query = query.filter(
                            VideoAnalyticsSummary.session_start == session_start
                        )
                    
                    summaries = query.all()
                    self.write({'data': [s.to_dict() for s in summaries]})
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in analytics export: {e}")
            self.set_status(500)
            self.write({'error': str(e)})
