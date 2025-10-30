from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
from datetime import datetime

app = Flask(__name__)

# In-memory storage for disputes
disputes = {}
dispute_counter = 0

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_dispute', methods=['POST'])
def create_dispute():
    global dispute_counter
    
    userA = request.form.get('userA')
    userB = request.form.get('userB')
    c = float(request.form.get('c'))
    s = float(request.form.get('s'))
    
    dispute_id = dispute_counter
    dispute_counter += 1
    
    disputes[dispute_id] = {
        'userA': userA,
        'userB': userB,
        'v1': None,  # Player 1's minimum acceptable - to be set
        'v2': None,  # Player 2's maximum offer - to be set
        'c': c,      # Initial claim by Player 1 (public)
        's': s,      # Initial offer by Player 2 (public)
        'player1_setup': False,
        'player2_setup': False,
        'min_value': s,
        'max_value': c,
        'rounds': [],
        'status': 'setup',
        'created_at': datetime.now().isoformat()
    }
    
    return render_template('dispute_created.html', 
                         dispute_id=dispute_id, 
                         userA=userA, 
                         userB=userB,
                         c=c,
                         s=s)

@app.route('/dispute/<int:dispute_id>/<username>/setup', methods=['POST'])
def submit_setup(dispute_id, username):
    if dispute_id not in disputes:
        return "Dispute not found", 404
    
    dispute = disputes[dispute_id]
    
    if username != dispute['userA'] and username != dispute['userB']:
        return "Invalid user", 403
    
    is_player1 = username == dispute['userA']
    
    if is_player1:
        dispute['v1'] = float(request.form.get('private_value'))
        dispute['player1_setup'] = True
    else:
        dispute['v2'] = float(request.form.get('private_value'))
        dispute['player2_setup'] = True
    
    # Check if both players have completed setup
    if dispute['player1_setup'] and dispute['player2_setup']:
        dispute['status'] = 'active'
    
    return redirect(url_for('dispute_view', dispute_id=dispute_id, username=username))

@app.route('/dispute/<int:dispute_id>/<username>')
def dispute_view(dispute_id, username):
    if dispute_id not in disputes:
        return "Dispute not found", 404
    
    dispute = disputes[dispute_id]
    
    # Simple validation - just check if username matches
    if username != dispute['userA'] and username != dispute['userB']:
        return "Invalid user", 403
    
    is_player1 = username == dispute['userA']
    
    # Handle setup phase
    if dispute['status'] == 'setup':
        player_setup_complete = dispute['player1_setup'] if is_player1 else dispute['player2_setup']
        other_setup_complete = dispute['player2_setup'] if is_player1 else dispute['player1_setup']
        
        return render_template('setup.html',
                             dispute_id=dispute_id,
                             username=username,
                             dispute=dispute,
                             is_player1=is_player1,
                             player_setup_complete=player_setup_complete,
                             other_setup_complete=other_setup_complete)
    
    # Calculate slider bounds based on private values
    if is_player1:
        slider_min = max(dispute['s'], dispute['v1'])
        slider_max = dispute['c']
    else:
        slider_min = dispute['s']
        slider_max = min(dispute['c'], dispute['v2'])
    
    # Check if user has already bid in current round
    current_round = len(dispute['rounds'])
    user_has_bid = False
    waiting_for_other = False
    
    if dispute['rounds'] and dispute['rounds'][-1]['status'] == 'bidding':
        last_round = dispute['rounds'][-1]
        if is_player1:
            user_has_bid = last_round['b1'] is not None
            waiting_for_other = user_has_bid and last_round['b2'] is None
        else:
            user_has_bid = last_round['b2'] is not None
            waiting_for_other = user_has_bid and last_round['b1'] is None
    
    # Check if waiting for vote
    waiting_for_vote = False
    user_has_voted = False
    if dispute['rounds'] and dispute['rounds'][-1]['status'] == 'voting':
        last_round = dispute['rounds'][-1]
        if is_player1:
            user_has_voted = last_round['vote1'] is not None
            waiting_for_vote = not user_has_voted
        else:
            user_has_voted = last_round['vote2'] is not None
            waiting_for_vote = not user_has_voted
    
    private_value = dispute['v1'] if is_player1 else dispute['v2']
    
    return render_template('dispute.html',
                         dispute_id=dispute_id,
                         username=username,
                         dispute=dispute,
                         is_player1=is_player1,
                         private_value=private_value,
                         slider_min=slider_min,
                         slider_max=slider_max,
                         user_has_bid=user_has_bid,
                         waiting_for_other=waiting_for_other,
                         waiting_for_vote=waiting_for_vote,
                         user_has_voted=user_has_voted)

@app.route('/dispute/<int:dispute_id>/<username>/bid', methods=['POST'])
def submit_bid(dispute_id, username):
    if dispute_id not in disputes:
        return "Dispute not found", 404
    
    dispute = disputes[dispute_id]
    
    if username != dispute['userA'] and username != dispute['userB']:
        return "Invalid user", 403
    
    if dispute['status'] != 'active':
        return redirect(url_for('dispute_view', dispute_id=dispute_id, username=username))
    
    is_player1 = username == dispute['userA']
    bid = float(request.form.get('bid'))
    
    # Validate bid is in range based on player's private value
    if is_player1:
        min_bid = dispute['v1']
        max_bid = dispute['c']
    else:
        min_bid = dispute['s']
        max_bid = dispute['v2']
    
    if bid < min_bid or bid > max_bid:
        return "Bid out of range", 400
    
    # Get or create current round
    if not dispute['rounds'] or dispute['rounds'][-1]['status'] != 'bidding':
        dispute['rounds'].append({
            'round_number': len(dispute['rounds']) + 1,
            'b1': None,
            'b2': None,
            'proposal': None,
            'vote1': None,
            'vote2': None,
            'status': 'bidding',
            'result': None
        })
    
    current_round = dispute['rounds'][-1]
    
    if is_player1:
        current_round['b1'] = bid
    else:
        current_round['b2'] = bid
    
    # Check if both bids are in
    if current_round['b1'] is not None and current_round['b2'] is not None:
        b1 = current_round['b1']
        b2 = current_round['b2']
        
        if b1 <= b2:
            # Propose settlement
            current_round['proposal'] = (b1 + b2) / 2
            current_round['status'] = 'voting'
        else:
            # Impasse - mark but don't end dispute
            current_round['status'] = 'impasse'
            current_round['result'] = 'impasse'
            # Dispute stays active - players can continue
    
    return redirect(url_for('dispute_view', dispute_id=dispute_id, username=username))

@app.route('/dispute/<int:dispute_id>/<username>/vote', methods=['POST'])
def submit_vote(dispute_id, username):
    if dispute_id not in disputes:
        return "Dispute not found", 404
    
    dispute = disputes[dispute_id]
    
    if username != dispute['userA'] and username != dispute['userB']:
        return "Invalid user", 403
    
    if dispute['status'] != 'active':
        return redirect(url_for('dispute_view', dispute_id=dispute_id, username=username))
    
    is_player1 = username == dispute['userA']
    vote = request.form.get('vote') == 'yes'
    
    current_round = dispute['rounds'][-1]
    
    if current_round['status'] != 'voting':
        return "Not in voting phase", 400
    
    if is_player1:
        current_round['vote1'] = vote
    else:
        current_round['vote2'] = vote
    
    # Check if both votes are in
    if current_round['vote1'] is not None and current_round['vote2'] is not None:
        if current_round['vote1'] and current_round['vote2']:
            # Agreement reached
            current_round['status'] = 'agreed'
            current_round['result'] = 'agreement'
            dispute['status'] = 'settled'
            dispute['settlement'] = current_round['proposal']
        else:
            # At least one NO vote
            current_round['status'] = 'rejected'
            current_round['result'] = 'rejected'
            # Continue to next round (stay active)
    
    return redirect(url_for('dispute_view', dispute_id=dispute_id, username=username))

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
