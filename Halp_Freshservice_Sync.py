"""
#
# Halp Freshservice Sync Helper 
#
"""

# NOTE: Debug logging via print() as Zapier doesn't integrate logging lib output

# NOTE: TypeError is raised "off-label" in several spots, as it's one of the few 
#       exception types that logs a traceback in Zapier (unlike ValueError)

import os   # Only used when local testing for getting secrets via os.getenv()
import re
import requests

# Initialize secrets when run locally. When using in Zapier, it will explicitly 
# pass input_data, and ignore the initialization below. Otherwise, read secrets 
# from local env variables, and if those are not found, throw an exception. 

try:
    input_data
except NameError:
    try:
        input_data = {
            "FRESHSERVICE_API_KEY" : os.environ["FRESHSERVICE_API_KEY"],
            "SLACK_HALP_TOKEN" : os.environ["SLACK_HALP_TOKEN"],
        }
    except KeyError:
        print("\nYou must configure Freshservice & Slack secrets as "
              "environment variables when testing locally!\n")
        raise
    IS_ZAPIER = False
else:
    IS_ZAPIER = True

# Initialize constants

HALP_EMAIL = "yourhalpemail@inbound.halp-mail.com"   # Set to your Halp inbound email 
FRESHSERVICE_HOSTNAME = "yourfreshservice.freshservice.com"   # Set to your Freshservice
REQUESTERS_URL = "https://" + FRESHSERVICE_HOSTNAME + "/api/v2/requesters"
FRESHSERVICE_AGENT_REQUESTER_EMAIL = "your.requester.email@company.com" 
DEBUG = False   # Enables/disables debug logging
DEBUG_DEEP = False   # Enables/disables deeper debug logging in get_requesters()

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

    next_cursor = "Initial"   # Init next_cursor for Slack user.list pagination
    
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
                return user["profile"]["email"].replace("tophat.com", 
                                                        "tophatmonocle.com")
            if "(" or ")" in user["profile"]["real_name_normalized"]:
                user["profile"]["real_name_normalized"] = \
                user["profile"]["real_name_normalized"].replace("(","")
                user["profile"]["real_name_normalized"] = \
                user["profile"]["real_name_normalized"].replace(")","")
            if slack_name in user["profile"]["real_name_normalized"]:
                return user["profile"]["email"].replace("tophat.com", 
                                                        "tophatmonocle.com")
    
        # Parse pagination cursor & handle end-of-list / non-paginated results,
        # as well as raise an exception if no match is found. 

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
        # If running in Zapier, ignore DEBUG_DEEP, otherwise ALL logging will be 
        # disabled in the app, as Zapier does not like print() within functions
        if DEBUG_DEEP and not IS_ZAPIER: 
                print(f"requester.json():\n{requester.json()}\n")
                print(f"requester_parsed:\n{requester_parsed}\n")
    except KeyError:
        print(f"Provided requester email address ({email}) "
              f"is not in a valid email address format!\n")
        raise

    # Return parsed requester dict (requester lookups always return a list of 
    # dicts, even though email-based lookups only return a single object - hence 
    # the 0 index). If no email found, return 'None' or raise an exception.

    if requester_parsed:
        return requester_parsed[0]
    else:
        if email is HALP_EMAIL:
            raise TypeError(f"\n\nRequester profile for {HALP_EMAIL} does not "
                             "exist! Try sending a reply or creating a new "
                             "ticket in Halp.\n")
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


def update_secondary_emails(existing_requester_id, email_type, secondary_emails):  # Must rename back away from secondary_emails, as it also updated primary if no requester
    """
    Update secondary emails in a Freshservice requester profile via API  
   
    Args:
        existing_requester_id (int): requester's Freshservice profile ID
        email_type (str): 
        secondary_emails (str/list of str): list of secondary emails to set

    Returns:
        updated_requester_parsed (dict): Updated, parsed requester profile
    """

    try:
        updated_requester = requests.put(
            f"{REQUESTERS_URL}/{existing_requester_id}", 
            auth=(input_data["FRESHSERVICE_API_KEY"],""), 
            json={email_type:secondary_emails}
            )
        updated_requester_parsed = updated_requester.json()["requester"]
    except:
            print("Updating requester failed!\n")
            if KeyError:
                print(f"\nError returned: \n{updated_requester.json()}\n")
            raise

    return updated_requester_parsed


# Get current requester info

if DEBUG:   # Pad debug output with a blank line for clarity
    print("")
current_requester = get_requester(HALP_EMAIL)
if DEBUG:
    print(f"current_requester\n{current_requester}\n")

# Lookup current requester email address from Slack. If requester doesn't have 
# a name (which happens for close ticket notifications), associate with email of
# Freshservice agent-requester (a previously created requester profile for an 
# agent, named "{FirstName} {LastName} [Halp]" and having an email address of
# first.last@halp.domain.com, since Freshservice doesn't allow merging profiles 
# into an agent profile.

if current_requester["first_name"] != HALP_EMAIL:
    slack_email = lookup_email_from_slack(current_requester["first_name"],
                                          current_requester["last_name"])
else:
    slack_email = FRESHSERVICE_AGENT_REQUESTER_EMAIL
if DEBUG:
    print(f"slack_email: {slack_email}\n")

# Get existing requester info via Slack email if requester profile exists

existing_requester = get_requester(slack_email)
if DEBUG:
    print(f"existing_requester\n{existing_requester}\n")

# If Slack user doesn't have a corresponding Freshservice requester profile,

if existing_requester is None:
    tokenized_email = re.search(r"^(?P<username>[^@]+)@(?P<domain>.*)"
                                r"\.(?P<tld>\w+)$",slack_email)
    halp_domain_tld_email = f"{tokenized_email.group('username')}" \
                             "@halp" \
                            f".{tokenized_email.group('domain')}" \
                            f".{tokenized_email.group('tld')}"

    existing_requester = get_requester(halp_domain_tld_email)
    if DEBUG:
        print(f"existing_requester\n{existing_requester}\n")

    if existing_requester is None:
        merged_requester = {"id": current_requester["id"]}
        email_type = "primary_email"
        requester_exists = False
    else:
        requester_exists = True

    secondary_emails = halp_domain_tld_email

else:
    secondary_emails = slack_email
    requester_exists = True

if requester_exists:
    if current_requester["id"] != existing_requester["id"]:
        merged_requester = merge_requesters(existing_requester["id"], 
                                            current_requester["id"])
        if DEBUG:
            print(f"merged_requester\n{merged_requester}\n")
    elif HALP_EMAIL in current_requester["secondary_emails"]:
        merged_requester = {
            "secondary_emails": current_requester["secondary_emails"],
            "id": current_requester["id"]
            }

    merged_requester["secondary_emails"].remove(HALP_EMAIL)

    if not merged_requester["secondary_emails"]:
        if "tophatmonocle.com" in secondary_emails:
            secondary_emails = [secondary_emails.replace("tophatmonocle.com", 
                                                         "tophat.com")]
        elif "bluedoorpublishing.com" in secondary_emails:
            secondary_emails = [secondary_emails.replace("bluedoorpublishing.com", 
                                                         "bluedoorcloud.com")]     
    else:
        secondary_emails = merged_requester["secondary_emails"]

    email_type = "secondary_emails"

cleaned_requester = update_secondary_emails(merged_requester["id"], email_type, 
                                            secondary_emails)
if DEBUG:
    print(f"updated_requester\n{cleaned_requester}\n")
