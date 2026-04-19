from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from models import db, init_db, User, Event, Booking
from datetime import datetime
from functools import wraps
import os

# Determine if running on Heroku (production)
is_production = os.getenv('HEROKU', False)

app = Flask(__name__, static_folder='static', template_folder='build')
print(app)

# Enhanced CORS configuration
if is_production:
    # Update with your actual Heroku app domain
    cors_origins = [
        "https://your-app-name.herokuapp.com",
        "http://your-app-name.herokuapp.com"
    ]
else:
    cors_origins = [
        "http://localhost:3000", 
        "http://localhost:3001", 
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:3001"
    ]

cors_config = {
    "origins": cors_origins,
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"],
    "supports_credentials": True
}
CORS(app, resources={r"/*": cors_config})

# Initialize database
init_db(app)

def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        if not user or not user.is_admin:
            return jsonify({'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Authentication Routes
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'message': 'Username, email, and password are required'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already exists'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email already exists'}), 400

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'User created successfully'}), 201

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'message': 'Invalid credentials'}), 401

    access_token = create_access_token(identity=str(user.id))
    return jsonify({
        'access_token': access_token,
        'user': user.to_dict()
    }), 200

@app.route('/auth/profile', methods=['GET'])
@jwt_required()
def get_profile():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({'message': 'User not found'}), 404
    return jsonify(user.to_dict()), 200

# Event Routes
@app.route('/events', methods=['GET'])
def get_events():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')
    date_filter = request.args.get('date', '')

    query = Event.query

    if search:
        query = query.filter(
            db.or_(
                Event.title.contains(search),
                Event.description.contains(search),
                Event.location.contains(search)
            )
        )

    if date_filter:
        try:
            filter_date = datetime.fromisoformat(date_filter.replace('Z', '+00:00'))
            query = query.filter(db.func.date(Event.date) == filter_date.date())
        except:
            pass

    events = query.order_by(Event.date).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'events': [event.to_dict() for event in events.items],
        'total': events.total,
        'pages': events.pages,
        'current_page': events.page
    }), 200

@app.route('/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    event = Event.query.get_or_404(event_id)
    return jsonify(event.to_dict()), 200

@app.route('/events', methods=['POST'])
@jwt_required()
def create_event():
    current_user_id = int(get_jwt_identity())
    data = request.get_json()

    title = data.get('title')
    description = data.get('description')
    date_str = data.get('date')
    location = data.get('location')
    price = data.get('price', 0.0)
    capacity = data.get('capacity', 100)
    image_url = data.get('image_url')

    if not title or not date_str:
        return jsonify({'message': 'Title and date are required'}), 400

    try:
        event_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        return jsonify({'message': 'Invalid date format'}), 400

    event = Event(
        title=title,
        description=description,
        date=event_date,
        location=location,
        price=price,
        capacity=capacity,
        image_url=image_url,
        created_by=current_user_id
    )

    db.session.add(event)
    db.session.commit()

    return jsonify(event.to_dict()), 201

@app.route('/events/<int:event_id>', methods=['PUT'])
@jwt_required()
def update_event(event_id):
    current_user_id = int(get_jwt_identity())
    event = Event.query.get_or_404(event_id)

    # Check if user is admin or event creator
    user = User.query.get(current_user_id)
    if not user.is_admin and event.created_by != current_user_id:
        return jsonify({'message': 'Permission denied'}), 403

    data = request.get_json()

    if 'title' in data:
        event.title = data['title']
    if 'description' in data:
        event.description = data['description']
    if 'date' in data:
        try:
            event.date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
        except:
            return jsonify({'message': 'Invalid date format'}), 400
    if 'location' in data:
        event.location = data['location']
    if 'price' in data:
        event.price = data['price']
    if 'capacity' in data:
        event.capacity = data['capacity']
    if 'image_url' in data:
        event.image_url = data['image_url']

    db.session.commit()
    return jsonify(event.to_dict()), 200

@app.route('/events/<int:event_id>', methods=['DELETE'])
@admin_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    return jsonify({'message': 'Event deleted successfully'}), 200

# Booking Routes
@app.route('/events/<int:event_id>/book', methods=['POST'])
@jwt_required()
def book_event(event_id):
    current_user_id = int(get_jwt_identity())
    event = Event.query.get_or_404(event_id)

    # Check if event is full
    booking_count = Booking.query.filter_by(event_id=event_id, status='confirmed').count()
    if booking_count >= event.capacity:
        return jsonify({'message': 'Event is fully booked'}), 400

    # Check if user already booked
    existing_booking = Booking.query.filter_by(
        event_id=event_id,
        user_id=current_user_id,
        status='confirmed'
    ).first()
    if existing_booking:
        return jsonify({'message': 'Already booked for this event'}), 400

    booking = Booking(
        event_id=event_id,
        user_id=current_user_id,
        payment_status='completed' if event.price == 0 else 'pending'
    )

    db.session.add(booking)
    db.session.commit()

    return jsonify({
        'message': 'Booking successful',
        'booking': booking.to_dict()
    }), 201

@app.route('/bookings', methods=['GET'])
@jwt_required()
def get_user_bookings():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)

    if user.is_admin:
        bookings = Booking.query.all()
    else:
        bookings = Booking.query.filter_by(user_id=current_user_id).all()

    return jsonify([booking.to_dict() for booking in bookings]), 200

@app.route('/events/<int:event_id>/bookings', methods=['GET'])
def get_event_bookings(event_id):
    """Get all bookings for a specific event (public endpoint)"""
    event = Event.query.get_or_404(event_id)
    bookings = Booking.query.filter_by(event_id=event_id, status='confirmed').all()
    return jsonify([booking.to_dict() for booking in bookings]), 200

@app.route('/bookings/<int:booking_id>', methods=['DELETE'])
@jwt_required()
def cancel_booking(booking_id):
    current_user_id = int(get_jwt_identity())
    booking = Booking.query.get_or_404(booking_id)

    # Check permission
    user = User.query.get(current_user_id)
    if not user.is_admin and booking.user_id != current_user_id:
        return jsonify({'message': 'Permission denied'}), 403

    booking.status = 'cancelled'
    db.session.commit()

    return jsonify({'message': 'Booking cancelled successfully'}), 200

# Admin Routes
@app.route('/admin/stats', methods=['GET'])
@admin_required
def get_admin_stats():
    total_events = Event.query.count()
    total_users = User.query.count()
    total_bookings = Booking.query.filter_by(status='confirmed').count()

    return jsonify({
        'total_events': total_events,
        'total_users': total_users,
        'total_bookings': total_bookings
    }), 200

@app.route('/admin/events', methods=['GET'])
@admin_required
def get_all_events_admin():
    events = Event.query.all()
    return jsonify([event.to_dict() for event in events]), 200

# Serve React frontend
@app.route('/')
def serve_index():
    return send_from_directory(app.template_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path != '' and os.path.exists(os.path.join(app.template_folder, path)):
        return send_from_directory(app.template_folder, path)
    return send_from_directory(app.template_folder, 'index.html')

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=port, debug=debug)