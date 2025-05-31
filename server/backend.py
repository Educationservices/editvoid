from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.json_util import dumps
import hashlib
from datetime import datetime
import os
from dotenv import load_dotenv
import certifi

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='../client', static_url_path='')
CORS(app)

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DB_NAME = os.getenv('DB_NAME', 'discord_clone')

# Initialize MongoDB client
client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]

# Collections
accounts = db['accounts']
messages = db['messages']
friends = db['friends']
settings = db['settings']

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_by_username(username):
    """Get user data by username"""
    return accounts.find_one({'username': {'$regex': f'^{username}$', '$options': 'i'}})

@app.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'message': 'Username and password are required'
            })
        
        if len(username) < 3:
            return jsonify({
                'success': False,
                'message': 'Username must be at least 3 characters long'
            })
        
        if len(password) < 6:
            return jsonify({
                'success': False,
                'message': 'Password must be at least 6 characters long'
            })
        
        # Check if username already exists
        if accounts.find_one({'username': {'$regex': f'^{username}$', '$options': 'i'}}):
            return jsonify({
                'success': False,
                'message': 'Username already exists'
            })
        
        # Create new account
        new_account = {
            'username': username,
            'password': hash_password(password),
            'created_at': datetime.now(),
            'profile_picture': '',
            'status': 'online'
        }
        
        account_id = accounts.insert_one(new_account).inserted_id
        
        # Initialize user settings
        settings.insert_one({
            'username': username,
            'theme': 'dark',
            'failsafe_key': 'ctrl+`',
            'failsafe_url': 'https://www.google.com',
            'notifications': True
        })
        
        # Initialize friends list
        friends.insert_one({
            'username': username,
            'friends': [],
            'pending_sent': [],
            'pending_received': []
        })
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'message': 'Username and password are required'
            })
        
        user = accounts.find_one({
            'username': {'$regex': f'^{username}$', '$options': 'i'},
            'password': hash_password(password)
        })
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'Invalid username or password'
            })
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'username': user['username'],
            'profile_picture': user.get('profile_picture', '')
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/send_message', methods=['POST'])
def send_message():
    """Send a new message"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        message = data.get('message', '').strip()
        
        if not username or not message:
            return jsonify({
                'success': False,
                'message': 'Username and message are required'
            })
        
        # Get user profile picture
        user = accounts.find_one({'username': {'$regex': f'^{username}$', '$options': 'i'}})
        profile_picture = user.get('profile_picture', '') if user else ''
        
        new_message = {
            'username': username,
            'message': message,
            'timestamp': datetime.now(),
            'channel': 'general',
            'profile_picture': profile_picture
        }
        
        messages.insert_one(new_message)
        
        # Keep only the last 100 messages
        message_count = messages.count_documents({})
        if message_count > 100:
            oldest_messages = messages.find().sort('_id', 1).limit(message_count - 100)
            messages.delete_many({'_id': {'$in': [msg['_id'] for msg in oldest_messages]}})
        
        return jsonify({
            'success': True,
            'message': 'Message sent successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/get_messages', methods=['GET'])
def get_messages():
    """Get all messages"""
    try:
        all_messages = list(messages.find().sort('timestamp', 1))
        # Convert ObjectId to string for JSON serialization
        for msg in all_messages:
            msg['_id'] = str(msg['_id'])
        
        return jsonify({
            'success': True,
            'messages': all_messages
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}',
            'messages': []
        })

@app.route('/update_profile_picture', methods=['POST'])
def update_profile_picture():
    """Update user's profile picture"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        profile_picture = data.get('profile_picture', '').strip()
        
        if not username:
            return jsonify({
                'success': False,
                'message': 'Username is required'
            })
        
        result = accounts.update_one(
            {'username': {'$regex': f'^{username}$', '$options': 'i'}},
            {'$set': {'profile_picture': profile_picture}}
        )
        
        if result.modified_count == 0:
            return jsonify({
                'success': False,
                'message': 'User not found or no changes made'
            })
        
        return jsonify({
            'success': True,
            'message': 'Profile picture updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/send_friend_request', methods=['POST'])
def send_friend_request():
    """Send a friend request"""
    try:
        data = request.get_json()
        sender = data.get('sender', '').strip()
        receiver = data.get('receiver', '').strip()
        
        if not sender or not receiver:
            return jsonify({
                'success': False,
                'message': 'Sender and receiver are required'
            })
        
        if sender.lower() == receiver.lower():
            return jsonify({
                'success': False,
                'message': 'Cannot send friend request to yourself'
            })
        
        # Check if receiver exists
        receiver_user = accounts.find_one({'username': {'$regex': f'^{receiver}$', '$options': 'i'}})
        if not receiver_user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            })
        
        # Get sender's friends data
        sender_friends = friends.find_one({'username': sender})
        if not sender_friends:
            sender_friends = {
                'username': sender,
                'friends': [],
                'pending_sent': [],
                'pending_received': []
            }
            friends.insert_one(sender_friends)
        
        # Get receiver's friends data
        receiver_friends = friends.find_one({'username': receiver})
        if not receiver_friends:
            receiver_friends = {
                'username': receiver,
                'friends': [],
                'pending_sent': [],
                'pending_received': []
            }
            friends.insert_one(receiver_friends)
        
        # Check if already friends
        if receiver in sender_friends['friends']:
            return jsonify({
                'success': False,
                'message': 'Already friends with this user'
            })
        
        # Check if request already sent
        if receiver in sender_friends['pending_sent']:
            return jsonify({
                'success': False,
                'message': 'Friend request already sent'
            })
        
        # Check if receiver already sent request to sender
        if sender in receiver_friends['pending_sent']:
            # Auto-accept and become friends
            friends.update_one(
                {'username': sender},
                {'$addToSet': {'friends': receiver}, '$pull': {'pending_received': receiver}}
            )
            friends.update_one(
                {'username': receiver},
                {'$addToSet': {'friends': sender}, '$pull': {'pending_sent': sender}}
            )
            
            return jsonify({
                'success': True,
                'message': f'Friend request accepted! You are now friends with {receiver}'
            })
        
        # Send friend request
        friends.update_one(
            {'username': sender},
            {'$addToSet': {'pending_sent': receiver}}
        )
        friends.update_one(
            {'username': receiver},
            {'$addToSet': {'pending_received': sender}}
        )
        
        return jsonify({
            'success': True,
            'message': f'Friend request sent to {receiver}'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/accept_friend_request', methods=['POST'])
def accept_friend_request():
    """Accept a friend request"""
    try:
        data = request.get_json()
        receiver = data.get('receiver', '').strip()
        sender = data.get('sender', '').strip()
        
        if not receiver or not sender:
            return jsonify({
                'success': False,
                'message': 'Receiver and sender are required'
            })
        
        # Verify the request exists
        receiver_data = friends.find_one({
            'username': receiver,
            'pending_received': sender
        })
        
        if not receiver_data:
            return jsonify({
                'success': False,
                'message': 'Friend request not found'
            })
        
        # Add to friends lists
        friends.update_one(
            {'username': receiver},
            {'$addToSet': {'friends': sender}, '$pull': {'pending_received': sender}}
        )
        friends.update_one(
            {'username': sender},
            {'$addToSet': {'friends': receiver}, '$pull': {'pending_sent': receiver}}
        )
        
        return jsonify({
            'success': True,
            'message': f'You are now friends with {sender}'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/decline_friend_request', methods=['POST'])
def decline_friend_request():
    """Decline a friend request"""
    try:
        data = request.get_json()
        receiver = data.get('receiver', '').strip()
        sender = data.get('sender', '').strip()
        
        if not receiver or not sender:
            return jsonify({
                'success': False,
                'message': 'Receiver and sender are required'
            })
        
        # Remove from pending lists
        friends.update_one(
            {'username': receiver},
            {'$pull': {'pending_received': sender}}
        )
        friends.update_one(
            {'username': sender},
            {'$pull': {'pending_sent': receiver}}
        )
        
        return jsonify({
            'success': True,
            'message': 'Friend request declined'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/get_friends', methods=['GET'])
def get_friends():
    """Get user's friends and pending requests"""
    try:
        username = request.args.get('username', '').strip()
        
        if not username:
            return jsonify({
                'success': False,
                'message': 'Username is required'
            })
        
        user_friends = friends.find_one({'username': username})
        
        if not user_friends:
            friends.insert_one({
                'username': username,
                'friends': [],
                'pending_sent': [],
                'pending_received': []
            })
            user_friends = friends.find_one({'username': username})
        
        # Get profile pictures and status for friends
        friends_with_pics = []
        for friend in user_friends['friends']:
            friend_data = accounts.find_one({'username': friend})
            friends_with_pics.append({
                'username': friend,
                'profile_picture': friend_data.get('profile_picture', '') if friend_data else '',
                'status': friend_data.get('status', 'offline') if friend_data else 'offline'
            })
        
        return jsonify({
            'success': True,
            'friends': friends_with_pics,
            'pending_sent': user_friends['pending_sent'],
            'pending_received': user_friends['pending_received']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/update_settings', methods=['POST'])
def update_settings():
    """Update user settings"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        new_settings = data.get('settings', {})
        
        if not username:
            return jsonify({
                'success': False,
                'message': 'Username is required'
            })
        
        result = settings.update_one(
            {'username': username},
            {'$set': new_settings},
            upsert=True
        )
        
        return jsonify({
            'success': True,
            'message': 'Settings updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

@app.route('/get_settings', methods=['GET'])
def get_settings():
    """Get user settings"""
    try:
        username = request.args.get('username', '').strip()
        
        if not username:
            return jsonify({
                'success': False,
                'message': 'Username is required'
            })
        
        user_settings = settings.find_one({'username': username})
        
        if not user_settings:
            default_settings = {
                'username': username,
                'theme': 'dark',
                'failsafe_key': 'ctrl+`',
                'failsafe_url': 'https://www.google.com',
                'notifications': True
            }
            settings.insert_one(default_settings)
            user_settings = default_settings
        
        # Remove MongoDB _id field
        if '_id' in user_settings:
            del user_settings['_id']
        
        return jsonify({
            'success': True,
            'settings': user_settings
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })


@app.route('/')
def serve_index():
    """Serve the main index.html file"""
    try:
        return send_from_directory(app.static_folder, 'index.html')
    except FileNotFoundError:
        return jsonify({
            'message': 'Frontend not found. Please build the client files.',
            'status': 'Backend is running',
            'endpoints': [
                '/register - POST - Register new user',
                '/login - POST - Login user',
                '/send_message - POST - Send message',
                '/get_messages - GET - Get all messages',
                '/update_profile_picture - POST - Update profile picture',
                '/send_friend_request - POST - Send friend request',
                '/accept_friend_request - POST - Accept friend request',
                '/decline_friend_request - POST - Decline friend request',
                '/get_friends - GET - Get friends and requests',
                '/update_settings - POST - Update user settings',
                '/get_settings - GET - Get user settings'
            ]
        }), 404

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    print("Starting Enhanced Discord Clone Server with MongoDB...")
    print("Server will run on http://localhost:5000")
    print("\nDirectory structure:")
    print(f"Static files served from: {os.path.abspath(app.static_folder)}")
    
    # Verify static folder exists
    if not os.path.exists(app.static_folder):
        print(f"\nWARNING: Static folder not found at {app.static_folder}")
        print("Please ensure your client files are built in the correct location.")
        print("The backend API will still work, but frontend won't be served.")
    
    print("\nPress Ctrl+C to stop the server")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
