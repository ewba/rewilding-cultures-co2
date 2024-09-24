#!/bin/python
import csv
import sys
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support.select import Select

# DEPENDENCY INFO:
# install geckodriver or chromedriver
#    pip install selenium
# debian et co with externally managed eggs:
#    sudo apt install python3-selenium firefox-esr-geckodriver
# if you're not using the snap version of a browser, download the driver manually and
# put it into your $PATH; you might also need to extract the selenium-manager
# of your platform from an official release of python3-selenium
# TODO: add caching, since the final legs are often likely to be the same?
# TODO: add any diagnostics for duplicates etc.? Running it again is a good way to catch them

if len(sys.argv) == 1:
    print("Make sure to pass the input data file path! Bailing out.")
    print("calc-co2.py [-n] inputFile [resultFile [eventName]]")
    sys.exit(1)

args = sys.argv
quitter = True
for arg in args:
    if arg == "-n":
        quitter = False
        del sys.argv[sys.argv.index(arg)]
        break

inputCSV = sys.argv[1]
if len(sys.argv) > 2:
    resultsFile = sys.argv[2]
else:
    resultsFile = "results.csv"
if len(sys.argv) > 3:
    event = sys.argv[3]
else:
    event = ""

browser = webdriver.Firefox()

# rewrite header for easier work and to avoid skipping duplicates
header = ['Submitted', 'Name', 'Event', 'E-mail', 'Legs', 'End0', 'End1', 'Passengers1', 'End2', 'Passengers2', 'End3', 'Passengers3', 'End4', 'Passengers4', 'End5', 'Passengers5', 'End6', 'Passengers6', 'End7', 'Passengers7', 'End8', 'Passengers8', 'End9', 'Passengers9', 'End10', 'Passengers10', 'Mode1', 'Fuel1', 'Mode2', 'Fuel2', 'Mode3', 'Fuel3', 'Mode4', 'Fuel4', 'Mode5', 'Fuel5', 'Mode6', 'Fuel6', 'Mode7', 'Fuel7', 'Mode8', 'Fuel8', 'Mode9', 'Fuel9', 'Mode10', 'Fuel10']

errorValue = -10000000000

def waitForVisible(timeout, el):
    WebDriverWait(browser, timeout).until(expected_conditions.visibility_of_element_located(el))

# fake wait hack (for some reason implicit wait did not work)
def fakeWait(delay = 5):
    try:
        waitForVisible(delay, (By.XPATH, "//non-existing"))
    except:
        pass

def parseEntry(row, writer):
    legs = int(row["Legs"])
    total = 0
    kms = 0
    for i in range(legs):
        # append commas to avoid selecting common rooted names that sort earlier for short inputs
        start = row["End" + str(i)] + ","
        end = row["End" + str(i + 1)] + ","
        mode = row["Mode" + str(i + 1)]
        fuel = row["Fuel" + str(i + 1)]
        try:
            passengers = int(row["Passengers" + str(i + 1)])
        except:
            passengers = 1
        #start = "Tolmin,"
        #end = "London,"
        #mode = "Bus"
        # fuel = "Electricity"
        legEmissions, km = prepCalc(start, end, mode, fuel, passengers)
        writer.writerow({ 'Event': row["Event"], 'Name': row["Name"], 'From': start[:-1], 'To': end[:-1], 'Mode': mode, 'Fuel': fuel, 'People': passengers, 'CO2': legEmissions, 'Kilometers': km })
        total = total + legEmissions
        kms = kms + km
    return total, kms

def runTest(start, end, mode, fuel):
    browser.get("https://travelandclimate.org/")
    assert 'Travel' in browser.title

    # 1 person
    browser.find_element(By.ID, "people").click()
    browser.find_element(By.ID, "people").send_keys("1")

    # set one-way trip
    browser.find_element(By.ID, "ways").click()
    browser.find_element(By.CSS_SELECTOR, "#ways > :nth-child(2)").click()

    # set start
    browser.find_element(By.ID, "origin").click()
    browser.find_element(By.ID, "origin").send_keys(start)
    fakeWait(1)
    waitForVisible(10, (By.CSS_SELECTOR, ".pac-item:nth-child(1)"))
    browser.find_element(By.CSS_SELECTOR, ".pac-item:nth-child(1)").click()

    # set destination
    browser.find_element(By.ID, "destinations.0").click()
    browser.find_element(By.ID, "destinations.0").send_keys(end)
    fakeWait(1)
    waitForVisible(10, (By.CSS_SELECTOR, ".pac-item:nth-child(1)"))
    destEl = browser.find_element(By.CSS_SELECTOR, ".pac-item:nth-child(1)")
    # sigh, child blocks it, but luckily is not a full overlay
    elH = destEl.rect["height"]
    elW = destEl.rect["width"]
    ActionChains(browser).move_to_element_with_offset(destEl, - elW // 4, elH // 2 - 1).click().perform()

    # ignore sleep and trigger calc
    browser.find_element(By.XPATH, "//button[contains(text(), 'Calculate')]").click()

    # wait for initial calc and then choose transport type
    # to id xpath in dev tools: $x("some xpath")
    # normal car:
    button = "t-driving"
    scaleFactor = 1
    originalMode = mode
    colSelector = ".column-driving .bg-drivingcar, .column-driving .bg-carferrycar"
    if mode == "Car":
        pass
    elif mode == "Bus" or mode == "Train":
        # NOTE: sometimes only offers a train for bus rides,
        # probably vice-versa as well. However the emission factors are
        # similar, so we don't mind
        button = "t-public-transport"
        colSelector = ".column-public-transport .bg-publictransport"
    elif mode == "Plane":
        # NOTE: includes shuttle to city if relevant
        # FIXME: long flights can have so high emissions the chart offsets elements enough
        # for this to fail, eg. with Houston to Athens
        button = "t-flying"
        colSelector = ".column-flying > .bg-flying"
    elif mode == "Ferry":
        # taken into account internally under Car
        # FIXME: unless there's no other option, then there's an independent ferry button
        # hit pe. with Helsinki - Tallinn
        return 0, 0
    elif mode == "Motorbike":
        # NOTE: comparing average fuel consumption is tricky, after some scouring
        # we take half of the car value
        mode = "Car"
        scaleFactor = 0.5
    elif mode == "Bike" or mode == "Walk":
        mode = "Car"
    else:
        print("unknown mode! " + mode)
        return errorValue, errorValue

    # actually pick ride type
    if mode == "Plane":
        pass
        #import pdb; pdb.set_trace()
    fakeWait(2)
    waitForVisible(10, (By.CLASS_NAME, button))
    ride = browser.find_element(By.CLASS_NAME, button)
    if ride:
        ride.click()
    else:
        print("No known connection for leg type: " + mode)
        return errorValue, errorValue

    # extra steps to get length of leg and pick fuel
    # NOTE: there could be more than one to pick (eg. with interim ferries, for airport access or changing buses)

    # open details column overlay and extract leg distance
    # there can be more than one valid bar (common with buses or if a ferry interrupts cars)
    fakeWait(2)
    waitForVisible(5, (By.CSS_SELECTOR, colSelector))
    #import pdb; pdb.set_trace()
    bars = browser.find_elements(By.CSS_SELECTOR, colSelector)
    km = 0
    seenKMs = [] # hack to avoid occasional double counting
    for bar in bars:
        if not bar.is_displayed() or "hidden" in bar.get_dom_attribute("class"):
            continue
        ActionChains(browser).move_to_element(bar).perform()
        fakeWait(2)
        # yuck, occasional XPATH failure, so we have to filter manually
        kmEls = bar.find_elements(By.XPATH, "//div/div/div[contains(text(), ' km')]")
        for kmEl in kmEls:
            if " km" in kmEl.text and kmEl.text not in seenKMs:
                seenKMs.append(kmEl.text)
                km += int(kmEl.text.split()[0])
                break

    # change fuel if not diesel
    otherFuels = [ "Petrol", "Natural gas", "Biogas", "Ethanol", "Biodiesel", "Electricity" ]
    if mode == "Car" and fuel in otherFuels:
        # translate to actual values
        fuelIdx = otherFuels.index(fuel)
        otherFuels = [ "gasoline", "gas (fossil)", "gas (bio)", "ethanol", "hvo 100", "electricity" ]

        # pick fuel
        els = browser.find_element(By.XPATH, "//select[contains(@*,'selectedDrivingFuel')]")
        select = Select(els)
        select.select_by_visible_text(otherFuels[fuelIdx])
        fakeWait(2)

    # choose random useless accommodation, so we can trigger the final calculation
    browser.find_element(By.CLASS_NAME, "t-accommodation").click()
    resultH2 = '//h2[small[text()="kg"]]'
    waitForVisible(5, (By.XPATH, resultH2))

    # grab and clean up the result
    emissions = browser.find_element(By.XPATH, resultH2).text
    kg = round(int(emissions.split()[0]) * scaleFactor)
    if originalMode == "Bike" or originalMode == "Walk":
        km = 0
    return (kg, km)

def prepCalc(start, end, mode, fuel, passengers):
    print("From {} to {} with {} ({}) and {} people: ".format(start, end, mode, fuel, passengers), end='')
    try:
        emissions, km = runTest(start, end, mode, fuel)
    except:
        emissions = km = errorValue

    emissions = round(emissions / passengers)
    print("{} kg from travelling {} km".format(emissions, km))
    return (emissions, km)

#######################################################################
# main startup
#######################################################################

# prepare a file to save results in and also to skip calculations if done
outHeader = [ "Event", "Name", "From", "To", "Mode", "Fuel", "People", "CO2", "Kilometers" ]
# sigh, ensure it exists, since python can't open it for appending otherwise
open(resultsFile, 'a').close()
with open(resultsFile, 'r') as outFile:
    resultStr = outFile.read()

rc = 0
with open(inputCSV, newline='') as inFile, open(resultsFile, 'a', newline='') as outFile:
    reader = csv.DictReader(inFile, header)
    writer = csv.DictWriter(outFile, fieldnames=outHeader)
    if not resultStr:
        writer.writeheader()

    rows = 0
    total = 0
    kms = 0
    for row in reader:
        if rows == 0:
            # skip bad header
            rows = 1
            continue

        # skip non-matching events
        if event and row["Event"] != event:
            continue

        # is the result already calculated?
        mentions = resultStr.count(row["Name"])
        if mentions == int(row["Legs"]):
            continue
        elif mentions > 0 and mentions <= int(row["Legs"]):
            print("ERROR: partial results detected for {}, bailing out.".format(row["Name"]))
            print("Perhaps there are several input entries?")
            rc = 1
            break

        rows = rows + 1
        emissions, km = parseEntry(row, writer)
        print("Emissions {} kg from {} travelling {} km".format(emissions, row["Name"], km))
        outFile.flush()
        total = total + emissions
        kms = kms + km
        fakeWait(1) # just to be nice to the server
        # break
    print("Total emissions: {} kg from {}+ people travelling {} km".format(total, rows - 1, kms))

if quitter:
    browser.quit()
sys.exit(rc)
