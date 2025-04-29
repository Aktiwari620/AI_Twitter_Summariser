import os
from flask import Flask, redirect, url_for, session, request, render_template
from requests_oauthlib import OAuth1Session, OAuth1
import requests
import google.generativeai as genai

app = Flask(__name__)

app.secret_key = "FLASK_KEY"

CONSUMER_KEY = os.environ.get('CONSUMER_KEY')
CONSUMER_SECRET = os.environ.get('CONSUMER_SECRET')
CALLBACK_URL = os.environ.get('CALLBACK_URL')

# --- Gemini API Configuration ---
try:
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25') 
    print("Gemini API configured successfully.")
    GEMINI_ENABLED = True
except KeyError:
    print("WARNING: GEMINI_API_KEY environment variable not set. Summarization will be disabled.")
    GEMINI_ENABLED = False
except Exception as e:
    print(f"WARNING: Error configuring Gemini API: {e}. Summarization will be disabled.")
    GEMINI_ENABLED = False


@app.route('/')
def home():
    """Initiate OAuth 1.0a by fetching a request token and redirecting to Twitter."""
    oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri=CALLBACK_URL)
    request_token_url = 'https://api.twitter.com/oauth/request_token'
    try:
        fetch_response = oauth.fetch_request_token(request_token_url)
        session['request_token'] = fetch_response
        authorization_url = oauth.authorization_url('https://api.twitter.com/oauth/authenticate')
        return redirect(authorization_url)
    except Exception as e:
        return f'Error getting request token. Check logs for details. Error: {str(e)}' # Show generic message

@app.route('/callback')
def callback():
    """Handle Twitter callback, exchange request token for access token."""
    try:
        oauth = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=session['request_token']['oauth_token'],
            resource_owner_secret=session['request_token']['oauth_token_secret'],
            verifier=request.args.get('oauth_verifier') # Twitter sends verifier in callback
        )
        access_token_url = 'https://api.twitter.com/oauth/access_token'
        access_token_response = oauth.fetch_access_token(access_token_url)

        session['access_token'] = access_token_response['oauth_token']
        session['access_token_secret'] = access_token_response['oauth_token_secret']
        session.pop('request_token', None)
        return redirect(url_for('summary'))
    except Exception as e:
        error_message = f'Error getting access token. Please ensure your Callback URL is set correctly in Twitter Developer Portal ({CALLBACK_URL}). Error: {str(e)}'
        return error_message, 500

@app.route('/summary')
def summary():
    """Fetch tweets, generate summary using Gemini, and display."""
    # Check if user is authenticated
    if 'access_token' not in session or 'access_token_secret' not in session:
        return redirect(url_for('home'))

    # Set up OAuth 1.0a authentication for API calls
    auth = OAuth1(
        CONSUMER_KEY,
        CONSUMER_SECRET,
        session['access_token'],
        session['access_token_secret']
    )

    # Step 1: Get the authenticated user's ID (using v2 endpoint)
    user_url = "https://api.twitter.com/2/users/me"
    user_id = None
    try:
        user_response = requests.get(user_url, auth=auth)
        user_response.raise_for_status()
        user_data = user_response.json()
        user_id = user_data['data']['id']
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching user ID: {e}")
        return f"Error fetching user ID: {str(e)} - Response: {e.response.text if e.response else 'No Response'}"
    except KeyError as e:
        return f"Error parsing user data: Missing key {e}. Response: {user_response.text}"
    except Exception as e:
        return f"An unexpected error occurred while fetching user data: {str(e)}"

    timeline_url = f"https://api.twitter.com/2/users/{user_id}/timelines/reverse_chronological"

    query_params = {
        'max_results': 50,
    }

    tweets = []
    timeline_error = None
    try:
        timeline_response = requests.get(timeline_url, auth=auth, params=query_params)
        timeline_response.raise_for_status()
        timeline_data = timeline_response.json()
        #timeline_data = {'data': [{'id': '1917334675485249932', 'edit_history_tweet_ids': ['1917334675485249932'], 'text': '‘It takes 10 months to lay hands on officers’: Supreme Court slams MP Police over custodial death https://t.co/5aPW6KTuE4'}, {'id': '1917333071210176686', 'edit_history_tweet_ids': ['1917333071210176686'], 'text': 'Mann says no to Saini request for water: ‘You used 103% of quota’ https://t.co/zQxb0BKfyS'}, {'id': '1917332794017034534', 'edit_history_tweet_ids': ['1917332794017034534'], 'text': 'Digha Jagannath temple to open today, CM Mamata Banerjee says: ‘All our guests’ https://t.co/mVEEFrPR4U'}, {'id': '1917332785578070520', 'edit_history_tweet_ids': ['1917332785578070520'], 'text': 'Horoscope Today 30 April, 2025: Aries, Cancer, Virgo and other sun signs – check astrological predictions https://t.co/IXsJLb5QQn'}, {'id': '1917332777961243011', 'edit_history_tweet_ids': ['1917332777961243011'], 'text': 'President Droupadi Murmu appoints Justice B R Gavai as next Chief Justice; will take oath on May 14 https://t.co/eziGaBhQTg'}, {'id': '1917330552933474703', 'edit_history_tweet_ids': ['1917330552933474703'], 'text': 'Let the man have his cashews. Marvel Studios’ #Thunderbolts* arrives only in theaters Friday. Get tickets now: https://t.co/bFq0RNfp6K https://t.co/7CBLrkXOEE'}, {'id': '1917330036387881275', 'edit_history_tweet_ids': ['1917330036387881275'], 'text': '#WATCH | Rajasthan | Gaurav Tanwar, a Fire Officer, says, "As soon as we received the fire information, we reached the spot. We started the operation to douse the fire. We are hopeful that by morning we will be able to control the situation..." https://t.co/CCATaJsZvT https://t.co/sFY2Ei6RaT'}, {'id': '1917327645710377245', 'edit_history_tweet_ids': ['1917327645710377245'], 'text': '#WATCH | Ahmedabad, Gujarat | Sharad Singhal, Joint CP (Crime) says, "Chandola lake is a government property. In the last 3-5 years, Gujarat ATS had arrested terrorists from here...A vast drug cartel has been busted here...In the past 3 years, a lot of drug cases have been lodged https://t.co/tVvgKnxwzE'}, {'id': '1917327623421563126', 'edit_history_tweet_ids': ['1917327623421563126'], 'text': 'Full focus. https://t.co/K6UatThWCm'}, {'id': '1917327578718671297', 'edit_history_tweet_ids': ['1917327578718671297'], 'text': 'BJP slams Congress over X poster of ‘missing’ PM https://t.co/Eej4GmQhDF'}, {'id': '1917326847420850288', 'edit_history_tweet_ids': ['1917326847420850288'], 'text': 'PM Modi: Govt modernising education system for 21st century needs https://t.co/wJTSitItcZ'}, {'id': '1917326838461784560', 'edit_history_tweet_ids': ['1917326838461784560'], 'text': 'Delhi Confidential: Route Change https://t.co/MGE7DhuVMQ'}, {'id': '1917326827527233797', 'edit_history_tweet_ids': ['1917326827527233797'], 'text': 'Amid BJP fire, Congress tells leaders to toe party’s line on Pahalgam https://t.co/ed2MuH5c01'}, {'id': '1917322624717185237', 'edit_history_tweet_ids': ['1917322624717185237'], 'text': '#WATCH | Rajasthan | A massive fire broke out at a factory in the Palra Industrial area of Ajmer. Fire tenders are present at the spot. Operations are underway to douse the fire. More details awaited. https://t.co/3tIEGEq6TV'}, {'id': '1917322103336100036', 'edit_history_tweet_ids': ['1917322103336100036'], 'text': '#WATCH | Rajasthan | A massive fire broke out at a factory in the Palra Industrial area of Ajmer. Fire tenders are present at the spot. Operations are underway to douse the fire. More details awaited. https://t.co/TW1KV7HOTa'}, {'id': '1917318512953156062', 'edit_history_tweet_ids': ['1917318512953156062'], 'text': 'Don’t miss Florence Pugh’s performance in Marvel Studios’ #Thunderbolts* ⚡️\n\nOnly in theaters Friday. Get tickets now: https://t.co/wDb2uh7B3v https://t.co/UiGjODYnGL'}, {'id': '1917316292790411391', 'edit_history_tweet_ids': ['1917316292790411391'], 'text': '#HBDNeerajakona @NeerajaKona \n\n#TelusuKada Will be a crazy outing for us can’t wait for the TrackOoOoOoOo to be on playlists 🙌🏿 https://t.co/X7rQ9jWfnf'}, {'id': '1917311727936356802', 'edit_history_tweet_ids': ['1917311727936356802'], 'text': 'Court rejects discharge applications by seven accused, including Oreva group MD, in Morbi bridge tragedy https://t.co/69YWArXqVi'}, {'id': '1917309866810527947', 'edit_history_tweet_ids': ['1917309866810527947'], 'text': 'RT @rightarmleftist: Just IN:— 🚨 The woman, Minal Ahmed Khan, married the CRPF jawan in May 2024 via video chat and later visited India on…'}, {'id': '1917309520201531415', 'edit_history_tweet_ids': ['1917309520201531415'], 'text': 'How a wedding video helped Gujarat’s Navsari police track down murder accused who jumped parole 27 years ago https://t.co/geLxIsBaX4'}, {'id': '1917308607877582953', 'edit_history_tweet_ids': ['1917308607877582953'], 'text': 'Beggars’ Home in Surat, 300-year-old haveli in Ahmedabad: Where Gujarat Police has housed people picked up in drive against illegal immigrants https://t.co/AT5kU6sUW1'}, {'id': '1917308596951404618', 'edit_history_tweet_ids': ['1917308596951404618'], 'text': 'Maharashtra govt scraps Re 1 crop insurance; switches back to old system https://t.co/4P1Vcb6gNq'}, {'id': '1917308589397471679', 'edit_history_tweet_ids': ['1917308589397471679'], 'text': 'Aligarh: 15-yr-old boy assaulted, ‘forced to urinate’ on Pakistan flag, say police https://t.co/GWc90xKvoa'}, {'id': '1917306590413078745', 'edit_history_tweet_ids': ['1917306590413078745'], 'text': 'Didi depression pe gyan de rhi thi— \n\nkya lagta hai abhi khud ye depression me hogi?? 😂 https://t.co/fjqsiA9Ec1'}, {'id': '1917306084605452671', 'edit_history_tweet_ids': ['1917306084605452671'], 'text': "Kamindu Mendis 🤝 Dushmantha Chameera\n\nWe just can't pick which catch was better! 🤔\n\nWhat's your take, folks❓\n\n#TATAIPL | #CSKvSRH | #DCvKKR | @SunRisers | @DelhiCapitals https://t.co/ARfLQPeZwc"}, {'id': '1917304113509060797', 'edit_history_tweet_ids': ['1917304113509060797'], 'text': 'RT @heyitsjennalynn: #Thunderbolts simultaneously broke &amp; healed something in me. Scrappy, with great action &amp; emotional nuance in a way th…'}, {'id': '1917303904364011902', 'edit_history_tweet_ids': ['1917303904364011902'], 'text': 'SP leaders’ Pahalgam attack remarks similar to Pak rhetoric: Yogi Adityanath https://t.co/FI2GsyyvOx'}, {'id': '1917303891265245585', 'edit_history_tweet_ids': ['1917303891265245585'], 'text': 'UP police receives ‘hoax’ threat message about bombs at Vapi textile units, 1 arrested https://t.co/JQU3if4GqJ'}, {'id': '1917303818532053047', 'edit_history_tweet_ids': ['1917303818532053047'], 'text': 'RT @SammyJReacts: #Thunderbolts is ABSOLUTE CINEMA. As emotionally resonant as it is entertaining. The thematic element of self-worth deliv…'}, {'id': '1917302472441200822', 'edit_history_tweet_ids': ['1917302472441200822'], 'text': '#WATCH | On being asked, the State Department\'s response to the Pakistan Minister\'s statement about performing dirty work for the United States while also denying the existence of Lashkar-e-Taiba in Pakistan, US State Department spokesperson Tammy Bruce says, "The Secretary of https://t.co/mng8pXVrkp'}, {'id': '1917302189451550826', 'edit_history_tweet_ids': ['1917302189451550826'], 'text': '20 days after coming to Kota, NEET aspirant hangs self; 13th suicide this year https://t.co/gCBScqsQd7'}, {'id': '1917300830987837586', 'edit_history_tweet_ids': ['1917300830987837586'], 'text': 'Nationalist Muslims in India were openly seen removing Pakistani flags from the road 🥰\n\nNow @zoo_bear will fact check and say: "They removed it because they thought it was an Islamic flag" 🤡\n\n https://t.co/DtRWtCMv9h'}, {'id': '1917300468893597762', 'edit_history_tweet_ids': ['1917300468893597762'], 'text': 'How KKR’s all-action hero Sunil Narine kept his team’s slim playoff hopes alive https://t.co/YPwD74CX0W'}, {'id': '1917300144527040662', 'edit_history_tweet_ids': ['1917300144527040662'], 'text': 'RT @IExpressSports: How #KKR’s all-action hero #SunilNarine kept his team’s slim playoff hopes alive | By @namitkumar_17 \n\nhttps://t.co/A6U…'}, {'id': '1917300036008042786', 'edit_history_tweet_ids': ['1917300036008042786'], 'text': '#WATCH | On the United States being in touch with the leadership of both Pakistan and India, US State Department spokesperson Tammy Bruce says, "That is correct. The secretary also gave me a note about that as well. So we are reaching out regarding the Kashmir situation, India https://t.co/E1FxQ2WZak'}, {'id': '1917299375988003073', 'edit_history_tweet_ids': ['1917299375988003073'], 'text': 'Children studying in govt schools in Maharashtra to get personalised health cards https://t.co/jZxmQ1aBm8'}, {'id': '1917299212909244707', 'edit_history_tweet_ids': ['1917299212909244707'], 'text': 'PAKISTAN MURDABAD! https://t.co/KkgaybXPIP'}, {'id': '1917298661484089786', 'edit_history_tweet_ids': ['1917298661484089786'], 'text': '‘Very hard thing to do’: Trump says not ‘looking’ at third term https://t.co/8pmd7WKNgu'}, {'id': '1917297334028795946', 'edit_history_tweet_ids': ['1917297334028795946'], 'text': 'Mumbai: Two booked for sexual assault and abuse in Wadala, police file swift chargesheets https://t.co/zBeTVgEnKE'}, {'id': '1917296627775332506', 'edit_history_tweet_ids': ['1917296627775332506'], 'text': 'A CRPF jawan’s Pakistani wife has been deported after visa violations.\n\nWhat the actual fuck? Such marriages can pose serious national security risks.\n\nKya chal rha h bhai ye sab is desh mein… https://t.co/S9EjoFMKid'}, {'id': '1917294869971607973', 'edit_history_tweet_ids': ['1917294869971607973'], 'text': 'Stoked for my boy competing in his first ever race finishing 3rd in his class, proud moment ❤️ https://t.co/E9AEK8IJFo'}, {'id': '1917294351438217679', 'edit_history_tweet_ids': ['1917294351438217679'], 'text': '1 killed as fire breaks out at Kolkata hotel https://t.co/inxaEav3Le'}, {'id': '1917294336972099868', 'edit_history_tweet_ids': ['1917294336972099868'], 'text': 'HC rejects plea seeking stay on demolition in Ahmedabad slum from where 890 were picked up in drive against illegal immigrants https://t.co/e5OSklLk9X'}, {'id': '1917294327635628056', 'edit_history_tweet_ids': ['1917294327635628056'], 'text': 'After Kalmadi gets clean chit: Congress leaders, aides raise decibel level to reinstate Suresh Kalmadi with dignity https://t.co/9EnD6sjrCA'}, {'id': '1917293310047121469', 'edit_history_tweet_ids': ['1917293310047121469'], 'text': 'Pakistan’s Foreign Minister, Ishaq Dar, says he had the name of the terror group TRF removed from the UNSC statement condemning the Pahalgam terror attack.\n\nIf it’s true, then by removing TRF’s name, Pakistan may be attempting to avoid international scrutiny or accusations that https://t.co/w6fFEAINtP'}, {'id': '1917292992295039170', 'edit_history_tweet_ids': ['1917292992295039170'], 'text': 'T 5264 -'}, {'id': '1917292133976805806', 'edit_history_tweet_ids': ['1917292133976805806'], 'text': 'एक औरत है केवल! आठ लाख कश्मीरी हिन्दुओं को भयावह नरसंहार के पश्चात् जब घाटी त्यागनी पड़ी, कब कोई कश्मीरी बाहर नहीं आया था। उसके बाद भी, हर वर्ष हत्याएँ होती रहीं, कोई बाहर नहीं आया था। https://t.co/IC4JudQUxB'}, {'id': '1917292104205885805', 'edit_history_tweet_ids': ['1917292104205885805'], 'text': 'ପୁରୀ ଲୋକସଭାର ନୟାଗଡ଼ ନିର୍ବାଚନ ମଣ୍ଡଳୀ ଅନ୍ତର୍ଗତ ଲାଠିପଡା ଗ୍ରାମ ପଂଚାୟତକୁ ଗସ୍ତ ସମୟରେ ସ୍ଥାନୀୟ ଜନସାଧାରଣଙ୍କର ଭବ୍ୟ ସ୍ୱାଗତ ତଥା ଭଲପାଇବା ପାଇଁ ସମସ୍ତଙ୍କୁ ମୋର ଅନ୍ତରରୁ ଧନ୍ୟବାଦ ଜଣାଉଛି ।\n\nଏହି ଅବସରରେ ଅନେକ ଦଶନ୍ଧି ଧରି ଚାଲି ଆସୁଥିବା ପବିତ୍ର ଅଷ୍ଟପ୍ରହରୀ କାର୍ଯ୍ୟକ୍ରମରେ ଶ୍ରଦ୍ଧାଳୁମାନଙ୍କ ସହ ସମ୍ମିଳିତ ହେବାର ସୁଯୋଗ https://t.co/kduR4aKBen'}, {'id': '1917291028060492126', 'edit_history_tweet_ids': ['1917291028060492126'], 'text': 'Maharashtra to establish trust to accelerate infra projects https://t.co/oKHwY8G71g'}, {'id': '1917288464472490186', 'edit_history_tweet_ids': ['1917288464472490186'], 'text': 'UP govt to denotify 11 historic buildings, repurpose them for heritage tourism https://t.co/5asmZGOrNB'}], 'meta': {'next_token': '7140dibdnow9c7btw4e02o4gme7gs6yztb5znbgbwa912', 'result_count': 50, 'newest_id': '1917334675485249932', 'oldest_id': '1917288464472490186'}}
        print(timeline_data)
        tweets = timeline_data.get('data', []) # v2 format
        print(f"Fetched {len(tweets)} tweets using v2 endpoint.")

    except requests.exceptions.RequestException as e:
        timeline_error = f"Error fetching timeline: {e.response.status_code if e.response else 'N/A'} - {e.response.text if e.response else str(e)}"
    except Exception as e:
        timeline_error = f"An unexpected error occurred fetching timeline: {str(e)}"


    # Step 3: Generate Summary with Gemini (if enabled and tweets exist)
    summary_text = "Summarization disabled or no tweets found."
    if GEMINI_ENABLED and tweets:
        # Prepare text for Gemini
        # Concatenate the 'text' field of each tweet
        full_text_for_summary = "\n\n---\n\n".join([tweet.get('text', '') for tweet in tweets if tweet.get('text')])

        # Create the prompt
        prompt = f"""
        Analyze the following collection of tweets from a User's Home Feed.
        Provide a concise summary highlighting the main themes, topics, significant news, or prevalent moods.
        Focus on the most important information. Structure the summary clearly, perhaps using bullet points if appropriate.
        Avoid simply listing tweets. Synthesize the information. Do not Include Any Other thing Just Directlu give Concise 
        Summaries in points if there's some Link give that as well. Act as you are a Personalized Summariser for the Tweeter.

        Tweets:
        -------
        {full_text_for_summary}
        -------

        Summary:
        """

        print("\n--- Sending text to Gemini for summarization ---")
        print("--- End of text ---")

        # Call Gemini API
        response = gemini_model.generate_content(prompt)
        summary_text = response.text
        print("\n--- Gemini Summary Received ---")
        print("--- End of Summary ---")


    elif not GEMINI_ENABLED:
         summary_text = "Summarization feature is currently disabled (API key not configured)."
    elif not tweets and not timeline_error:
         summary_text = "No tweets found in the timeline to summarize."
    elif timeline_error:
         summary_text = "Could not generate summary because the timeline could not be fetched."


    # Render the tweets and summary in the template
    return render_template('summary.html',
                           tweets=tweets,
                           summary=summary_text,
                           timeline_error=timeline_error,
                           gemini_enabled=GEMINI_ENABLED)

@app.route('/logout')
def logout():
    session.clear() # Clear the entire session
    return redirect(url_for('home'))

# if __name__ == '__main__':

#     app.run(debug=True, port=5000)
