from datetime import datetime, timedelta
import json
import logging
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user

# Configure logging
logger = logging.getLogger(__name__)

# Create blueprint
medicine_bp = Blueprint('medicine', __name__, url_prefix='/medicine')

def get_db():
    """Import this function from app.py when integrating with main app"""
    from app import get_db
    return get_db()

@medicine_bp.route('/')
@login_required
def index():
    db = get_db()
    routines = db.execute(
        """SELECT r.*, 
              (SELECT COUNT(*) FROM medicine_doses WHERE routine_id = r.id) as dose_count,
              (SELECT COUNT(*) FROM notifications 
               WHERE routine_id = r.id AND status = 'pending' 
               AND scheduled_time <= datetime('now', 'localtime')) as pending_notifications
           FROM medicine_routines r
           WHERE r.user_id = ? AND r.active = 1
           ORDER BY r.priority DESC, r.medicine_name ASC""",
        (current_user.id,)
    ).fetchall()
    
    today = datetime.now().strftime('%Y-%m-%d')
    upcoming = db.execute(
        """SELECT n.id, n.scheduled_time, n.status, r.medicine_name, r.priority, 
                  d.dosage, d.instructions, d.time_of_day
           FROM notifications n
           JOIN medicine_routines r ON n.routine_id = r.id
           JOIN medicine_doses d ON n.dose_id = d.id
           WHERE n.user_id = ? AND date(n.scheduled_time) = ? 
             AND n.status = 'pending'
           ORDER BY n.scheduled_time ASC
           LIMIT 5""",
        (current_user.id, today)
    ).fetchall()
    
    # Dosage stats for today
    taken_count = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND date(scheduled_time) = ? AND status = 'taken'",
        (current_user.id, today)
    ).fetchone()[0]
    remaining_count = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND date(scheduled_time) = ? AND status = 'pending'",
        (current_user.id, today)
    ).fetchone()[0]
    skipped_count = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND date(scheduled_time) = ? AND status = 'skipped'",
        (current_user.id, today)
    ).fetchone()[0]
    
    return render_template(
        'medicine_routine.html', 
        routines=routines,
        upcoming_notifications=upcoming,
        taken_count=taken_count,
        remaining_count=remaining_count,
        skipped_count=skipped_count
    )
@medicine_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add a new medicine routine"""
    if request.method == 'POST':
        medicine_name = request.form['medicine_name']
        description = request.form['description']
        priority = request.form['priority']
        start_date = request.form['start_date']
        end_date = request.form.get('end_date', '')
        
        # Process doses (from JSON format)
        doses = json.loads(request.form['doses'])
        
        db = get_db()
        try:
            # Start transaction
            db.execute("BEGIN")
            
            # Insert medicine routine
            cursor = db.execute(
                """INSERT INTO medicine_routines 
                   (user_id, medicine_name, description, priority, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (current_user.id, medicine_name, description, priority, start_date, 
                 end_date if end_date else None)
            )
            routine_id = cursor.lastrowid
            
            # Insert doses
            for dose in doses:
                cursor = db.execute(
                    """INSERT INTO medicine_doses
                       (routine_id, time_of_day, frequency_hours, dosage, instructions)
                       VALUES (?, ?, ?, ?, ?)""",
                    (routine_id,
                     dose['time_of_day'],
                     dose['frequency_hours'],  # changed from dose['frequency']
                     dose['dosage'],
                     dose.get('instructions', ''))
                )
                dose_id = cursor.lastrowid
                
                schedule_notifications(db, routine_id, dose_id,
                                       dose['time_of_day'],
                                       dose['frequency_hours'],  # changed from dose['frequency']
                                       start_date, end_date)
            # Commit transaction
            db.commit()
            
            flash('Medicine routine added successfully!', 'success')
            return redirect(url_for('medicine.index'))
            
        except Exception as e:
            db.execute("ROLLBACK")
            logger.error(f"Failed to add medicine routine: {str(e)}")
            flash(f'Failed to add medicine routine: {str(e)}', 'error')
    
    return render_template('add_medicine.html')

@medicine_bp.route('/edit/<int:routine_id>', methods=['GET', 'POST'])
@login_required
def edit(routine_id):
    """Edit an existing medicine routine"""
    db = get_db()
    
    # Check if the routine belongs to the current user
    routine = db.execute(
        "SELECT * FROM medicine_routines WHERE id = ? AND user_id = ?",
        (routine_id, current_user.id)
    ).fetchone()
    
    if not routine:
        flash('Medicine routine not found', 'error')
        return redirect(url_for('medicine.index'))
    
    if request.method == 'POST':
        medicine_name = request.form['medicine_name']
        description = request.form['description']
        priority = request.form['priority']
        start_date = request.form['start_date']
        end_date = request.form.get('end_date', '')
        
        # Process doses
        doses = json.loads(request.form['doses'])
        
        try:
            # Start transaction
            db.execute("BEGIN")
            
            # Update medicine routine
            db.execute(
                """UPDATE medicine_routines 
                   SET medicine_name = ?, description = ?, priority = ?,
                       start_date = ?, end_date = ?
                   WHERE id = ?""",
                (medicine_name, description, priority,
                 start_date, end_date if end_date else None, routine_id)
            )
            
            # Delete existing doses and notifications
            db.execute("DELETE FROM medicine_doses WHERE routine_id = ?", (routine_id,))
            db.execute("DELETE FROM notifications WHERE routine_id = ?", (routine_id,))
            
            # Insert new doses and generate notifications
            for dose in doses:
                cursor = db.execute(
                    """INSERT INTO medicine_doses
                       (routine_id, time_of_day, frequency_hours, dosage, instructions)
                       VALUES (?, ?, ?, ?, ?)""",
                    (routine_id,
                     dose['time_of_day'],
                     dose['frequency_hours'],  # fixed key name here
                     dose['dosage'],
                     dose.get('instructions', ''))
                )
                dose_id = cursor.lastrowid
                
                schedule_notifications(db, routine_id, dose_id,
                                       dose['time_of_day'],
                                       dose['frequency_hours'],  # fixed key name here
                                       start_date, end_date)
            
            # Commit transaction
            db.commit()
            
            flash('Medicine routine updated successfully!', 'success')
            return redirect(url_for('medicine.index'))
            
        except Exception as e:
            db.execute("ROLLBACK")
            logger.error(f"Failed to update medicine routine: {str(e)}")
            flash(f'Failed to update medicine routine: {str(e)}', 'error')
    
    # Get doses for this routine
    doses = db.execute(
        "SELECT * FROM medicine_doses WHERE routine_id = ?",
        (routine_id,)
    ).fetchall()
    
    return render_template('edit_medicine.html', routine=routine, doses=doses)

@medicine_bp.route('/delete/<int:routine_id>', methods=['POST'])
@login_required
def delete(routine_id):
    """Delete a medicine routine"""
    db = get_db()
    
    # Check if the routine belongs to the current user
    routine = db.execute(
        "SELECT * FROM medicine_routines WHERE id = ? AND user_id = ?",
        (routine_id, current_user.id)
    ).fetchone()
    
    if not routine:
        flash('Medicine routine not found', 'error')
        return redirect(url_for('medicine.index'))
    
    try:
        # Start transaction
        db.execute("BEGIN")
        
        # Delete the routine, doses, and notifications
        db.execute("DELETE FROM notifications WHERE routine_id = ?", (routine_id,))
        db.execute("DELETE FROM medicine_doses WHERE routine_id = ?", (routine_id,))
        db.execute("DELETE FROM medicine_routines WHERE id = ?", (routine_id,))
        
        # Commit transaction
        db.commit()
        
        flash('Medicine routine deleted successfully!', 'success')
    except Exception as e:
        db.execute("ROLLBACK")
        logger.error(f"Failed to delete medicine routine: {str(e)}")
        flash(f'Failed to delete medicine routine: {str(e)}', 'error')
    
    return redirect(url_for('medicine.index'))

@medicine_bp.route('/notification/update/<int:notification_id>', methods=['POST'])
@login_required
def update_notification(notification_id):
    """Update notification status (taken or skipped)"""
    data = request.get_json() or {}
    status = data.get('status', 'taken')
    
    db = get_db()
    
    # Check if notification belongs to user
    notification = db.execute(
        "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
        (notification_id, current_user.id)
    ).fetchone()
    
    if not notification:
        return jsonify({'success': False, 'message': 'Notification not found'})
    
    try:
        db.execute(
            "UPDATE notifications SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (status, notification_id)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Failed to update notification: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})
@medicine_bp.route('/notifications/pending')
@login_required
def pending_notifications():
    """Get pending notifications for the user (used for AJAX polling)"""
    db = get_db()
    
    # Get current pending notifications
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    notifications = db.execute(
        """SELECT n.id, n.scheduled_time, r.medicine_name, r.priority,
                  d.dosage, d.instructions
           FROM notifications n
           JOIN medicine_routines r ON n.routine_id = r.id
           JOIN medicine_doses d ON n.dose_id = d.id
           WHERE n.user_id = ? AND n.status = 'pending'
             AND datetime(n.scheduled_time) <= datetime(?, 'localtime')
           ORDER BY n.scheduled_time ASC""",
        (current_user.id, current_time)
    ).fetchall()
    
    result = []
    for note in notifications:
        # Update status to "sent"
        db.execute(
            "UPDATE notifications SET status = 'sent', sent_at = datetime('now', 'localtime') WHERE id = ? AND status = 'pending'",
            (note['id'],)
        )
        
        result.append({
            'id': note['id'],
            'time': note['scheduled_time'],
            'medicine': note['medicine_name'],
            'dosage': note['dosage'],
            'instructions': note['instructions'],
            'priority': note['priority']
        })
    
    db.commit()
    return jsonify(result)

@medicine_bp.route('/notifications/today')
@login_required
def today_notifications():
    """Get all of today's notifications for the user"""
    db = get_db()
    
    today = datetime.now().strftime('%Y-%m-%d')
    notifications = db.execute(
        """SELECT n.id, n.scheduled_time, n.status, r.medicine_name, r.priority,
                  d.dosage, d.instructions
           FROM notifications n
           JOIN medicine_routines r ON n.routine_id = r.id
           JOIN medicine_doses d ON n.dose_id = d.id
           WHERE n.user_id = ? AND date(n.scheduled_time) = ?
           ORDER BY n.scheduled_time ASC""",
        (current_user.id, today)
    ).fetchall()
    
    result = []
    for note in notifications:
        result.append({
            'id': note['id'],
            'time': note['scheduled_time'],
            'status': note['status'],
            'medicine': note['medicine_name'],
            'dosage': note['dosage'],
            'instructions': note['instructions'],
            'priority': note['priority']
        })
    
    return jsonify(result)

def schedule_notifications(db, routine_id, dose_id, time_of_day, frequency_hours, start_date, end_date=None):
    """Schedule notifications for a medicine dose"""
    # Convert to datetime objects
    start = datetime.strptime(start_date, '%Y-%m-%d')
    
    # If end_date is not specified, schedule for 30 days
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        end = start + timedelta(days=30)
    
    # Parse time of day
    hour, minute = map(int, time_of_day.split(':'))
    
    # Generate notification times
    current_date = start
    while current_date <= end:
        # Start with the first dose at the specified time
        current_time = datetime.combine(current_date.date(), datetime.strptime(time_of_day, '%H:%M').time())
        
        # Schedule doses throughout the day based on frequency
        while current_time.date() == current_date.date():
            if current_time >= datetime.now():
                # Only schedule future notifications
                db.execute(
                    """INSERT INTO notifications
                       (user_id, routine_id, dose_id, scheduled_time, status)
                       VALUES (?, ?, ?, ?, 'pending')""",
                    (current_user.id, routine_id, dose_id, current_time.strftime('%Y-%m-%d %H:%M'))
                )
            
            # Next dose after frequency_hours
            current_time += timedelta(hours=int(frequency_hours))
        
        # Move to next day
        current_date += timedelta(days=1)