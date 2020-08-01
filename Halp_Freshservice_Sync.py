import os   # Only used when local testing for getting secrets via os.getenv()
import re
import requests

# Initialize input_data dictionary for local testing. When using in Zapier, it 
# will pass input_data explicitly, and initialization will be ignored. For local
# testing, be sure to set local envir variables to Freshservice & Slack secrets. 

try:
    input_data
except NameError:
    input_data = {
        "FRESHSERVICE_API_KEY" : os.getenv("FRESHSERVICE_API_KEY"),
        "SLACK_HALP_TOKEN" : os.getenv("SLACK_HALP_TOKEN"),
    }

# Initialize constants

HALP_EMAIL = "top-hat@inbound.halp-mail.com"   # Set to your Halp inbound email 
FRESHSERVICE_HOSTNAME = "tophat.freshservice.com"   # Set to your Freshservice
REQUESTERS_URL = "https://" + FRESHSERVICE_HOSTNAME + "/api/v2/requesters"
FRESHSERVICE_AGENT_REQUESTER_EMAIL = "tom.spis@halp.tophatmonocle.com"
DEBUG = True   # Enables debug logging via print()
DEBUG_DEEP = True   # Enables deeper debug logging in get_requesters()

# Function definitions

def lookup_email_from_slack(current_first_name, current_last_name):
    """
    Looks up a Slack user email address using display/real name via API
    
    Tries to find a matching Slack user via their display name, and if 
    not found, via their real name. If a user with a matching name is 
    found, returns their email address. Exits with exception if not.

    Args:
        current_first_name (str): current requester's first name
        current_last_name (str): current requester's last name

    Returns:
        user["profile"]["email"] (str): Slack user's email address
    """

    slack_name = f"{current_first_name}" \
                 f"{' ' + current_last_name if current_last_name else ''}"

    next_cursor = "Initial" # Init next_cursor for Slack user.list pagination
    
    # Get & parse Slack's user.list (user list for entire Slack workspace). 
    # Receives a default of 1000 users/page (cursor-based pagination). Using 
    # requests lib instead of official Python Slack SDK for compat with Zapier.

    while True:
        if next_cursor == "Initial":
            users_list = requests.get(
                "https://slack.com/api/users.list", 
                params={"token":input_data["SLACK_HALP_TOKEN"]})
        else:
            users_list = requests.get(
                "https://slack.com/api/users.list", 
                params={"token":input_data["SLACK_HALP_TOKEN"], 
                "cursor":next_cursor})
        
        members_list = users_list.json()["members"]

        # Scan Slack user list page and search for matching display_name (after 
        # stripping parentheses, as Freshservice does automatically). If found, 
        # return associated email address early. If no match found, repeat strip 
        # & search for real_name, then return email address if found. Using 
        # ordered early returns in a single for-loop to balance readibility with
        # perf. Using '_normalized' variant for better compat w/non-ASCII chars. 

        for user in members_list:
            if "(" or ")" in user["profile"]["display_name_normalized"]:
                user["profile"]["display_name_normalized"] = \
                user["profile"]["display_name_normalized"].replace("(","")
                user["profile"]["display_name_normalized"] = \
                user["profile"]["display_name_normalized"].replace(")","")
            if slack_name in user["profile"]["display_name_normalized"]:
                return user["profile"]["email"]
            if "(" or ")" in user["profile"]["real_name_normalized"]:
                user["profile"]["real_name_normalized"] = \
                user["profile"]["real_name_normalized"].replace("(","")
                user["profile"]["real_name_normalized"] = \
                user["profile"]["real_name_normalized"].replace(")","")
            if slack_name in user["profile"]["real_name_normalized"]:
                return user["profile"]["email"]
    
        # Parse pagination cursor & handle end-of-list / non-paginated results,
        # as well as raise an exception if no match is found. Raising TypeError
        # off-label, as it's one of the few types that log errors in Zapier.   

        try:
            next_cursor = users_list.json()["response_metadata"]["next_cursor"]
            if not next_cursor:
                raise TypeError("\n\nUnable to find a matching Slack "
                                "display or real name!\n")
        except:
            if not TypeError: # Handles KeyError from single-page .json() result
                print("\nUnable to find a matching Slack "
                      "display or real name!\n")
            raise


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
        requester = requests.get(REQUESTERS_URL, 
                                 auth=(input_data["FRESHSERVICE_API_KEY"],""), 
                                 params={"email":email})
        requester_parsed = requester.json()["requesters"]
        if DEBUG_DEEP:
            print(f"requester.json():\n{requester.json()}\n")
            print(f"requester_parsed:\n{requester_parsed}\n")
    except KeyError:
        print(f"Provided requester email address ({email}) "
              f"is not in a valid email address format!\n")
        raise

    if requester_parsed and requester_parsed is not None:
        return requester_parsed[0]
    else:
        if email is HALP_EMAIL:
            raise ValueError(f"\n\nRequester profile for {HALP_EMAIL} "
                             f"does not exist!\n")
        return


def merge_requesters(existing_requester_id, current_requester_id):
    """
    Merge new Freshservice requester profile into existing one via API  
   
    Args:
        existing_requester_id (int): requester's Freshservice profile ID
        current_requester_id (int): current Freshservice profile ID

    Returns:
        merged_requester_parsed (dict): Merged, parsed requester profile
    """
    
    try:
        merged_requester = requests.put(
            f"{REQUESTERS_URL}/{existing_requester_id}/merge", 
            auth=(input_data["FRESHSERVICE_API_KEY"],""), 
            json={"secondary_requesters":current_requester_id}
            )
        merged_requester_parsed = merged_requester.json()["requester"]
    except:
            print("Merging requesters failed!\n")
            if KeyError:
                print(f"\nError returned: \n{merged_requester.json()}\n")
            raise

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
        updated_requester = requests.put(
            f"{REQUESTERS_URL}/{existing_requester_id}", 
            auth=(input_data["FRESHSERVICE_API_KEY"],""), 
            json={email_type:email_to_update}
            )
        updated_requester_parsed = updated_requester.json()["requester"]
    except:
            print("Updating requester failed!\n")
            if KeyError:
                print(f"\nError returned: \n{updated_requester.json()}\n")
            raise

    return updated_requester_parsed


current_requester = get_requester(HALP_EMAIL)
if DEBUG is True:
    print(f"current_requester\n{current_requester}\n")

if current_requester["first_name"] != HALP_EMAIL:
    slack_email = lookup_email_from_slack(current_requester["first_name"],
                                          current_requester["last_name"])
else:
    slack_email = FRESHSERVICE_AGENT_REQUESTER_EMAIL

if "tophat.com" in slack_email:
    slack_email = slack_email.replace("tophat.com", "tophatmonocle.com")
if DEBUG is True:
    print(f"\nslack_email: {slack_email}\n")

existing_requester = get_requester(slack_email)
if DEBUG is True:
    print(f"existing_requester\n{existing_requester}\n")

if existing_requester is None:
    tokenized_email = re.search(r"^(?P<username>[^@]+)@(?P<domain>.*)"
                                  "\.(?P<tld>\w+)$",slack_email)
    halp_domain_tld_email = f"{tokenized_email.group('username')}" \
                             "@halp" \
                            f".{tokenized_email.group('domain')}" \
                            f".{tokenized_email.group('tld')}"

    existing_requester = get_requester(halp_domain_tld_email)
    if DEBUG is True:
        print(f"existing_requester\n{existing_requester}\n")

    if existing_requester is None:
        merged_requester = {"id": current_requester["id"]}
        email_type = "primary_email"
        requester_exists = False
    else:
        requester_exists = True

    email_to_update = halp_domain_tld_email

else:
    email_to_update = slack_email
    requester_exists = True

if requester_exists:
    if current_requester["id"] != existing_requester["id"]:
        merged_requester = merge_requesters(existing_requester["id"], 
                                            current_requester["id"])
        if DEBUG is True:
            print(f"merged_requester\n{merged_requester}\n")
    elif HALP_EMAIL in current_requester["secondary_emails"]:
        merged_requester = {
            "secondary_emails": current_requester["secondary_emails"],
            "id": current_requester["id"]
            }

    merged_requester["secondary_emails"].remove(HALP_EMAIL)

    if not merged_requester["secondary_emails"]:
        if "tophatmonocle.com" in email_to_update:
            email_to_update = [email_to_update.replace("tophatmonocle.com", 
                                                       "tophat.com")]
        elif "bluedoorpublishing.com" in email_to_update:
            email_to_update = [email_to_update.replace("bluedoorpublishing.com", 
                                                       "bluedoorcloud.com")]     
    else:
        email_to_update = merged_requester["secondary_emails"]

    email_type = "secondary_emails"

updated_requester = update_email(merged_requester["id"], 
                                 email_type, email_to_update)
if DEBUG is True:
    print(f"updated_requester\n{updated_requester}\n")