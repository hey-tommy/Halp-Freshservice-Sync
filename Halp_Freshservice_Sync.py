import os   # Only necessary for os.getenv() for local testing
import re
import requests

# Initialize input_data dictionary for local testing. Comment out if using  
# via Zapier, and match Zap input accordingly. For local testing, be sure to 
# set local environment variables with Freshservice & Slack secrets. 

input_data = {
    "FRESHSERVICE_API_KEY" : os.getenv("FRESHSERVICE_API_KEY"),
    "SLACK_HALP_TOKEN" : os.getenv("SLACK_HALP_TOKEN"),
    "display_or_real_name" : "Tom SpisTester"   # Define Slack name to look up
}

# Slack names to try for testing
#   "Tom SpisTester"
#   "TomSpace"
#   "Joel he/him/his"

# Initialize constants

HALP_EMAIL = "top-hat@inbound.halp-mail.com"   # Set to your Halp inbound email 
FRESHSERVICE_HOSTNAME = "tophat.freshservice.com"   # Set to your Freshservice
REQUESTERS_URL = "https://" + FRESHSERVICE_HOSTNAME + "/api/v2/requesters"
DEBUG = True
DEBUG_DEEP = True

# Function Definitions

def lookup_email_from_slack(input_data):
    """
    Looks up a Slack user email address using display/real name via API
    
    Tries to find a matching Slack user via their display name, and if 
    not found, by their real name. If a user with a matching name is 
    found, returns their email address. If not found, returns 'None'.

    Args:
        input_data (dict of str): API secrets & Slack name (see above)

    Returns:
        user["profile"]["email"] (str): Slack user's email address
          or
        (None)
    """

    # Restore Freshservice-ommitted parentheses to Slack display names 
    # which originally contained them (edge case processing)

    edge_case_name_remap = {
        "Hood he/him/his" : "Hood (he/him/his)",
        "Joel he/him/his" : "Joel (he/him/his)",
        "Ralf he/him/his" : "Ralf (he/him/his)",
        "Wenyu Gu Fish" : "Wenyu Gu (Fish)" 
        }

    if input_data["display_or_real_name"] in edge_case_name_remap:
        input_data["display_or_real_name"] = edge_case_name_remap
        [input_data["display_or_real_name"]]

    # Initialize next_cursor for Slack user.list pagination

    next_cursor = ""
    
    # Get & parse Slack's user.list (user list for entire Slack workspace). 
    # Receives a default of 1000 users/page (cursor-based pagination).
    # Not using official Python Slack SDK for compatability with Zapier.

    while True:

        if next_cursor == "":
            users_list = requests.get("https://slack.com/api/users.list", 
            params={"token":input_data["SLACK_HALP_TOKEN"]})
        else:
            users_list = requests.get("https://slack.com/api/users.list", 
            params={"token":input_data["SLACK_HALP_TOKEN"], "cursor":next_cursor})
        
        members_list = users_list.json()["members"]

        # Search for matching display_name, and if not found, real_name - 
        # then return associated email address as soon as a match is found. 
        # Using '_normalized' variants for better compat with non-ASCII chars.
        
        for user in members_list:
                if input_data["display_or_real_name"] \
                    in user["profile"]["display_name_normalized"]:
                    return user["profile"]["email"]
                elif input_data["display_or_real_name"] \
                    in user["profile"]["real_name_normalized"]:
                    return user["profile"]["email"]
    
        # Parse pagination cursor & handle end-of-list / non-paginated results

        try:
            next_cursor = users_list.json()["response_metadata"]["next_cursor"]
            if next_cursor == "":
                return
        except:
            return


def get_requester(email):
    """
    Looks up Freshservice requester details using email address via API  
        
    Tries to find a matching Freshservice requester profile via email 
    address. If a matching requester profile is found, it is parsed and 
    returned. If not found, 'None' is returned.

    Args:
        email (str): Freshservice requester's primary email address

    Returns:
        requester_parsed[0] (dict): Parsed Freshservice requester profile
          or
        (None)
    """

    try:
        requester = requests.get(REQUESTERS_URL, auth=(input_data
        ["FRESHSERVICE_API_KEY"],""), params={"email":email})
        requester_parsed = requester.json()["requesters"]
        if DEBUG_DEEP is True:
                print(f"requester.json():\n{requester.json()}\n")
                print(f"requester_parsed:\n{requester_parsed}\n")
    except KeyError:
        raise Exception (f"\nProvided requester email address ({email}) \
        is not in a valid email address format!\n")

    if email is HALP_EMAIL:
        assert requester_parsed, f"Requester details for {HALP_EMAIL} not found!"

    if requester_parsed and requester_parsed is not None:
        return requester_parsed[0]
    else:
        return
# TODO: Add ability to search agents as requesters 


def merge_requesters(existing_requester_id, new_requester_id):
    """
    Merge new Freshservice requester profile into existing one using API  
   
    Args:
        existing_requester_id (int): requester's Freshservice profile ID
        new_requester_id (int): new (temp) Freshservice profile ID

    Returns:
        merged_requester_parsed (dict): Merged, parsed requester profile
    """
    
    assert new_requester_id != existing_requester_id, "Requesters are already merged!"
    
    try:
        merged_requester = requests.put(f"{REQUESTERS_URL}/{existing_requester_id}/merge", 
        auth=(input_data["FRESHSERVICE_API_KEY"],""), 
        json={"secondary_requesters":new_requester_id})
        merged_requester_parsed = merged_requester.json()["requester"]
    except KeyError:
            raise Exception (f"\nMerging requesters failed!\nError returned:\n \
                {merged_requester.json()}\n")

    return merged_requester_parsed


def update_email(existing_requester_id, email_type, email_to_update):
    """
    Update secondary emails in a Freshservice requester profile via API  
   
    Args:
        existing_requester_id (int): requester's Freshservice profile ID
        email_type (str): 
        email_to_update (str/list of str): list of secondary emails to set

    Returns:
        updated_requester_parsed (dict): Updated, parsed requester profile
    """

    try:
        updated_requester = requests.put(f"{REQUESTERS_URL}/{existing_requester_id}", 
        auth=(input_data["FRESHSERVICE_API_KEY"],""), 
        json={email_type:email_to_update})
        updated_requester_parsed = updated_requester.json()["requester"]
    except KeyError:
            raise Exception (f"\nUpdating requester failed!\nError returned:\n \
                {updated_requester.json()}\n")

    return updated_requester_parsed


slack_email = lookup_email_from_slack(input_data)

assert slack_email is not None, "Unable to find display name or real name in Slack!"
    
if "tophat.com" in slack_email:
    slack_email = slack_email.replace("tophat.com", "tophatmonocle.com")
if DEBUG is True:
    print(f"\nslack_email: {slack_email}\n")

new_requester = get_requester(HALP_EMAIL)
if DEBUG is True:
    print(f"new_requester\n{new_requester}\n")

existing_requester = get_requester(slack_email)
if DEBUG is True:
    print(f"existing_requester\n{existing_requester}\n")

if existing_requester is None:

    tokenized_email = re.search(r"^(?P<username>[^@]+)@(?P<domain>.*)\."
        "(?P<tld>\w{2,10})$",slack_email)
    halp_domain_tld_email = f"{tokenized_email.group('username')}@halp." \
        f"{tokenized_email.group('domain')}.{tokenized_email.group('tld')}"

    existing_requester = get_requester(halp_domain_tld_email)
    if DEBUG is True:
        print(f"existing_requester\n{existing_requester}\n")

    if existing_requester is None:
        merged_requester = {"id": new_requester["id"]}
        email_type = "primary_email"
        requester_exists = False
    else:
        requester_exists = True

    email_to_update = halp_domain_tld_email

else:
    email_to_update = slack_email
    requester_exists = True

if requester_exists is True:

    if new_requester["id"] != existing_requester["id"]:
        merged_requester = merge_requesters(existing_requester["id"],
            new_requester["id"])
        if DEBUG is True:
            print(f"merged_requester\n{merged_requester}\n")
    elif HALP_EMAIL in new_requester["secondary_emails"]:
        merged_requester = {"secondary_emails": new_requester["secondary_emails"]}

    merged_requester["secondary_emails"].remove(HALP_EMAIL)

    if not merged_requester["secondary_emails"]:
        if "tophatmonocle.com" in email_to_update:
            email_to_update = [email_to_update.replace
                ("tophatmonocle.com", "tophat.com")]
        elif "bluedoorpublishing.com" in slack_email:
            email_to_update = [email_to_update.replace
                ("bluedoorpublishing.com", "bluedoorcloud.com")]     
    else:
        email_to_update = merged_requester["secondary_emails"]

    email_type = "secondary_emails"

updated_requester = update_email(merged_requester["id"], email_type, email_to_update)
if DEBUG is True:
    print(f"updated_requester\n{updated_requester}\n")