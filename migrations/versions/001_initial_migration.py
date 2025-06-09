"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create cameras table
    op.create_table('cameras',
        sa.Column('id', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('ip', sa.String(15), nullable=False),
        sa.Column('location', sa.String(200), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cameras_ip'), 'cameras', ['ip'], unique=True)
    
    # Create detections table
    op.create_table('detections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.String(50), nullable=False),
        sa.Column('timestamp', sa.Integer(), nullable=False),
        sa.Column('image_path', sa.String(255), nullable=False),
        sa.Column('faces_count', sa.Integer(), nullable=True),
        sa.Column('test_mode', sa.Boolean(), nullable=True),
        sa.Column('real_camera', sa.Boolean(), nullable=True),
        sa.Column('schedule_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_camera_timestamp', 'detections', ['camera_id', 'timestamp'])
    op.create_index('idx_timestamp', 'detections', ['timestamp'])
    op.create_index('idx_schedule', 'detections', ['schedule_id'])
    
    # Create stream_sessions table
    op.create_table('stream_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.String(50), nullable=False),
        sa.Column('session_id', sa.String(100), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create detection_schedules table
    op.create_table('detection_schedules',
        sa.Column('id', sa.String(100), nullable=False),
        sa.Column('camera_ids', sa.Text(), nullable=False),
        sa.Column('duration', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('detection_schedules')
    op.drop_table('stream_sessions')
    op.drop_index('idx_schedule', table_name='detections')
    op.drop_index('idx_timestamp', table_name='detections')
    op.drop_index('idx_camera_timestamp', table_name='detections')
    op.drop_table('detections')
    op.drop_index(op.f('ix_cameras_ip'), table_name='cameras')
    op.drop_table('cameras') 