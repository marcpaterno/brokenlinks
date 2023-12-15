## brokenlinks web spider

The brokenlinks web spider is a Python tool to search a web site for broken links.
It identifies, for a given site, the links on all accessible pages that are in some way *bad*.
A link is *bad* if an attempt to access it yields any result other than an HTTP status of success.

## Getting the software

### Getting a working environment on macOS

We assume you have [homebrew](https://brew.sh) installed.
You will need both *git* and *Python 3* to get and use the software.
With Homebrew installed, do:

    brew install git
    brew install python3

### Getting the brokenlinks software

In a terminal window, in whatever directory you choose to work in, do the following.
Note you can cut and paste these instructions directly into a shell session:

    git clone https://git.com/marcpaterno/brokenlinks.git
    cd brokenlinks
    python3 -m venv local-venv
    source local-venv/bin/activate
    python -m pip install --editable ${PWD}

You only need to do this once on any given machine.

### Using the brokenlinks software

In a terminal, `cd` into the same `brokenlinks` directory you created when you obtained the software.
In that shell session, you must first *activate* the Python virtual environment in which you have installed the software.
Note the `#` line below is *shell comment*, and does not need to be executed.
However, you can cut and paste the whole block below; executing the shell comment has no effect:

    # In the directory you created above:
    source local-venv/bin/activate

Running the `brokenlinks` program is done as:

    python brokenlinks.py

This will scan the site, and write out a *comma separated values* (CSV) file named `results.csv`.
This fill will contain a header row followed by zero or more data rows.
There will be one data row for each bad link found.
The file will contain three columns:

#. the URL for the page on which the bad link was found,
#. the URL of the bad link itself, and
#. a status code indicating the nature of the *badness* of the link.

The status code will be either 999 (indicating that there was no response at all from the server address that is part of the bad link), or the HTTP status code that indicates that a server was reached, but something went wrong while accessing the resource pointed to by the URL.
A full listing of HTTP status codes can be found man places online; one useful one is https://en.wikipedia.org/wiki/List_of_HTTP_status_codes.


