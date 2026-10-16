# Scenario s1 review

_Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated._

For every needle: can a person find it from the visible events alone, before the deadline?
h = hours since day 0 (storm start, Sep 1 20:00), as in events.jsonl.

## Needles

### s1_n_01 · broken_promise · Mei Chen, 82 · 41-22 Hollow Oak Ln Bsmt, Sunnyside 11104
Son Wei promised Tue Sep 7, never came; block ETA pushed to Sep 13+ on Wed Sep 8; flooded meter keeps her dark; not answering from the evening of Tue Sep 7 until Wed Sep 22 09:00; answers then.  
**deadline h 528.0** · danger h 600.0 · response 24h · people at risk 1 · name variants: Mei Chen, Mrs. Chen, Chen Mei, Mei Chenn, the elderly woman in the basement

- **REQ** `s1_e_000376` h 42.6 (09-03T14:36) [visit_note] Visited Mrs. Chen, 82, at 41-22 Hollow Oak Lane. Lives alone, speaks mostly Mandarin. Basement flooded, no power since Wednesday night. Her son Wei is coming Tuesday to help clean out and take her to stay with him. Registered her for follow-up calls. Follow up Wednesday.
- **REQ** `s1_e_000818` h 158.7 (09-08T10:43) [utility] Con Edison outage update: restoration on Hollow Oak Ln, 41-01 to 41-99, Sunnyside 11104 delayed. Flooded equipment in multiple buildings. New estimate: Sep 13 or later.
- **REQ** `s1_e_001073` h 303.0 (09-14T11:00) [crew] Con Edison field crew: 4122 HOLLOW OAK LN meter room flooded, service not reconnected. Needs licensed electrician certification. No one answered the door.
- truth: h 3 flooded; h 3 power_out; h 43 promise (come help clean out and take her to stay with him); h 144 promise_broken; h 145 stops_answering_until; h 448 needs_supplies (food and water; running low); h 493 answers_again; h 594 power_restored

### s1_n_02 · broken_promise · Abdul Rahman, 74 · 89-66 Mistlecove Ave , Jamaica 11432
Oxygen concentrator user; battery promised Sat Sep 4, never delivered; block out until ~Sep 9.  
**deadline h 96.0** · danger h 120.0 · response 12h · people at risk 2 · name variants: Abdul Rahman, Mr. Rahman, A. Rahman, Abdul Rehman, the older man at 89-66

- **REQ** `s1_e_000029` h 1.7 (09-01T21:43) [utility] Con Edison outage update: 15 customers without power on Mistlecove Ave, 89-01 to 89-99, Jamaica 11432. Cause: flooding. Estimated restoration: Sep 4.
- **REQ** `s1_e_000152` h 14.2 (09-02T10:12) [311] 311 call from daughter of ABDUL RAHMAN at 89-66 MISTLECOVE AVE: power out since last night, father uses a home oxygen concentrator, backup tank running low.
- **REQ** `s1_e_000389` h 44.0 (09-03T15:59) [visit_note] Mr. Rahman, 89-66 Mistlecove Ave. Red Cross will deliver a portable battery unit Saturday. Daughter staying with him.
- truth: h 2 power_out; h 14 needs_supplies (portable battery for oxygen concentrator); h 44 promise (deliver portable battery unit); h 72 promise_broken; h 189 power_restored

### s1_n_03 · broken_promise · Gloria Hernandez, 34 · 57-95 Fernhollow St Bsmt, Corona 11368
Landlord promised plumber Fri Sep 10; sewage still there Sep 13; family of 5 with 2 kids.  
**deadline h 336.0** · danger h 408.0 · response 48h · people at risk 5 · name variants: Gloria Hernandez, Mrs. Hernandez, G. Hernandez, Gloria Hernandes, the lady in the basement

- **REQ** `s1_e_000708` h 113.0 (09-06T12:59) [crew] HPD inspection at 57-95 FERNHOLLOW ST, cellar unit (tenant Mrs. Hernandez): sewage on floor, no heat/hot water. Family of 5 incl. 2 children. Landlord states licensed plumber coming Friday.
- **REQ** `s1_e_001058` h 287.4 (09-13T19:24) [311] 311 call from GLORIA HERNANDES at 57-95 FERNHOLLOW ST: sewage still in apartment, nobody came to fix it, kids sleeping upstairs at neighbor's.
- truth: h 2 flooded; h 3 heat_out; h 113 promise (send licensed plumber); h 216 promise_broken

### s1_n_04 · broken_promise · Soon-ja Kim, 77 · 141-03 Bramblewick St Bsmt, Flushing 11354
Caseworker callback promised Thu Sep 9 never happened; the neighbor hosting her moves out ~Sep 18.  
**deadline h 384.0** · danger h 456.0 · response 48h · people at risk 1 · name variants: Soon-ja Kim, Mrs. Kim, Kim Soon-ja, the elderly woman in the basement

- **REQ** `s1_e_000450` h 63.0 (09-04T11:00) [visit_note] Mrs. Kim, 77, 14103 Bramblewick St. Basement unit unlivable, sleeping on a neighbor's couch upstairs. Caseworker will call her back Thursday about temporary housing. Speaks Korean, some English.
- **REQ** `s1_e_001096` h 325.0 (09-15T09:00) [311] 311 call re: 141-03 BRAMBLEWICK ST: elderly woman staying on my couch since the flood, I'm moving out end of the week, she has nowhere to go.
- truth: h 2 flooded; h 63 promise (call back about temporary housing); h 192 promise_broken

### s1_n_05 · cross_service_join · Luis Rodriguez, 81 · 25-61 Pebblebrook Pl Bsmt, East Elmhurst 11369
Wheelchair user alone by day in a dark basement; visible only when 311 (typo name, compact address), DEP, a nameless visit note, and the utility delay are joined.  
**deadline h 288.0** · danger h 360.0 · response 24h · people at risk 2 · name variants: Luis Rodriguez, Mr. Rodriguez, L. Rodriguez, Luis Rodrigez, the older man in the basement

- **REQ** `s1_e_000101` h 4.8 (09-02T00:48) [311] 311 call from JOSE RODRIGEZ at 2561 PEBBLEBROOK PL: water rising in basement, elderly father can't do stairs.
- **REQ** `s1_e_000502` h 67.0 (09-04T15:00) [crew] DEP crew pumped basement at 25-61 PEBBLEBROOK PL. Occupant Mr. Rodriguez uses a wheelchair, declined to leave.
- **REQ** `s1_e_000571` h 86.0 (09-05T09:58) [utility] Con Edison outage update: restoration on Pebblebrook Pl, 25-01 to 25-99, East Elmhurst 11369 delayed. Flooded equipment in multiple buildings. New estimate: Sep 15 or later.
- **REQ** `s1_e_000994` h 237.5 (09-11T17:29) [visit_note] Man in a wheelchair at 2561 Pebblebrook Pl. Basement unit, alone during the day, son works nights. Said he's fine, didn't want help.
- truth: h 1 power_out; h 2 flooded; h 321 power_restored

### s1_n_06 · cross_service_join · Nasima Hossain, 69 · 87-26 Lanternfield Ln 2F, Elmhurst 11373
Building dark (flooded panel) + insulin needs refrigeration; 311, Con Ed crew, and visit under name variants.  
**deadline h 216.0** · danger h 276.0 · response 24h · people at risk 1 · name variants: Nasima Hossain, Mrs. Hossain, N. Hossain, Nasima Hossein, the lady in 2F

- **REQ** `s1_e_000744` h 132.0 (09-07T08:00) [311] 311 call from N. HUSSAIN at 8726 LANTERNFIELD LN: no heat, no hot water, no electricity in building.
- **REQ** `s1_e_000827` h 160.0 (09-08T12:00) [crew] Con Edison field crew: 87-26 LANTERNFIELD LN building panel flooded; block service restored but building not reconnected pending electrician.
- **REQ** `s1_e_000883` h 186.0 (09-09T14:00) [visit_note] Mrs. Hussain at 8726 Lanternfield Ln, lives alone. Keeps her insulin in the fridge, fridge has been off for days.
- truth: h 2 power_out; h 2 heat_out; h 186 needs_supplies (refrigeration for insulin); h 424 power_restored

### s1_n_07 · cross_service_join · Guo Hua Wang, 84 · 43-41 Quailbrook St Bsmt, Elmhurst 11373
Vacate order + elderly couple sleeping in a stairwell; joined across 311, DOB, volunteer.  
**deadline h 240.0** · danger h 312.0 · response 48h · people at risk 2 · name variants: Guo Hua Wang, Mr. Wang, Wang Guo Hua, Guo Hua Wong, the older man in the basement

- **REQ** `s1_e_000572` h 86.0 (09-05T09:59) [311] 311 complaint at 43-41 QUAILBROOK ST BSMT: illegal conversion, elderly couple (the Wangs) living in cellar after flood.
- **REQ** `s1_e_000758` h 135.0 (09-07T11:00) [crew] DOB: vacate order issued for cellar unit at 43-41 QUAILBROOK ST BSMT. Occupants to relocate.
- **REQ** `s1_e_000843` h 164.0 (09-08T15:59) [visit_note] Older couple, the Wangs, 4341 Quailbrook St Bsmt. Had to leave the cellar, sleeping in the building's back stairwell. Only speak Mandarin.
- truth: h 2 flooded; h 164 needs_supplies (shelter; sleeping in stairwell)

### s1_n_08 · silent_household · Carmen Morales, 79 · 42-09 Jasperwell Ave Bsmt, Woodside 11377
Opted in Sep 2, then stops answering for 10 days while the block stays dark.  
**deadline h 168.0** · danger h 240.0 · response 24h · people at risk 1 · name variants: Carmen Morales, Mrs. Morales, C. Morales, the elderly woman in the basement

- **REQ** `s1_e_000027` h 1.6 (09-01T21:38) [utility] Con Edison outage update: 97 customers without power on Jasperwell Ave, 42-01 to 42-99, Woodside 11377. Cause: flooding. Estimated restoration: Sep 4.
- **REQ** `s1_e_000130` h 11.9 (09-02T07:54) [311] 311 call from CARMEN MORALES at 42-09 JASPERWELL AVE: Basement apartment flooded, no power, resident 79 lives alone.
- **REQ** `s1_e_000140` h 13.1 (09-02T09:06) [visit_note] Registered Mrs. Morales, 79, at 42-09 Jasperwell Ave for follow-up calls. Lives alone in the basement unit; no power since the storm.
- truth: h 2 power_out; h 2 flooded; h 40 stops_answering_until; h 280 answers_again; h 280 power_restored

### s1_n_09 · silent_household · Dawa Sherpa, 31 · 78-23 Willowmere St Bsmt, Jackson Heights 11372
Opted in Sep 3, then stops answering for 10 days while the block stays dark.  
**deadline h 192.0** · danger h 264.0 · response 24h · people at risk 3 · name variants: Dawa Sherpa, Mrs. Sherpa, D. Sherpa, the lady in the basement

- **REQ** `s1_e_000020` h 1.0 (09-01T21:02) [utility] Con Edison outage update: 74 customers without power on Willowmere St, 78-01 to 78-99, Jackson Heights 11372. Cause: flooding. Estimated restoration: Sep 3.
- **REQ** `s1_e_000327` h 39.4 (09-03T11:24) [311] 311 call from DAWA SHERPA at 78-23 WILLOWMERE ST: No water pressure and no power in basement unit, family of 3 with an infant.
- **REQ** `s1_e_000350` h 40.6 (09-03T12:36) [visit_note] Registered Mrs. Sherpa at 7823 Willowmere St for follow-up calls. Family of 3 with an infant in the basement unit; no water pressure, no power.
- truth: h 1 power_out; h 2 flooded; h 64 stops_answering_until; h 268 power_restored; h 304 answers_again

### s1_n_10 · silent_household · George Papadopoulos, 91 · 70-37 Gullwing Rd , Forest Hills 11375
Opted in Sep 2, then stops answering for 10 days while the block stays dark.  
**deadline h 168.0** · danger h 240.0 · response 24h · people at risk 1 · name variants: George Papadopoulos, Mr. Papadopoulos, G. Papadopoulos, George Papadopolous, the older man at 70-37

- **REQ** `s1_e_000054` h 2.6 (09-01T22:37) [utility] Con Edison outage update: 98 customers without power on Gullwing Rd, 70-01 to 70-99, Forest Hills 11375. Cause: flooding. Estimated restoration: Sep 3.
- **REQ** `s1_e_000121` h 11.2 (09-02T07:10) [311] 311 call from GEORGE PAPADOPOULOS at 7037 GULLWING RD: Tree down across the front steps, resident 91 uses a walker and can't get out.
- **REQ** `s1_e_000133` h 12.4 (09-02T08:22) [visit_note] Son Nick registered his father, Mr. Papadopoulos, 91, at 70-37 Gullwing Rd for follow-up calls. Uses a walker; the fallen tree still blocks the front steps.
- truth: h 3 power_out; h 40 stops_answering_until; h 248 power_restored; h 280 answers_again

## Decoys

### s1_d_01 · restored_outage · Ming Wu, 72 · 150-04 Wickerbay Rd 3R, Flushing 11355
No-power report; restored next day.

- **DECOY** `s1_e_000295` h 37.0 (09-03T09:00) [311] 311 call from WU MING at 15004 WICKERBAY RD: no power since the storm, senior lives alone.
- `s1_e_000441` h 62.0 (09-04T09:59) [crew] Con Edison field crew: service restored at 150-04 WICKERBAY RD.

### s1_d_02 · resolved_alarm · Frank Russo, 86 · 32-40 Oriole Crest Ave Bsmt, East Elmhurst 11369
Trapped-in-basement report; evacuated within hours.

- **DECOY** `s1_e_000074` h 3.1 (09-01T23:06) [311] 311 call from neighbor at 32-40 ORIOLE CREST AVE: elderly man trapped in basement, water rising.
- `s1_e_000110` h 6.0 (09-02T02:00) [crew] FDNY: resident at 32-40 ORIOLE CREST AVE evacuated safely, staying with daughter in Bayside.

### s1_d_03 · kept_promise · Xiu Ying Liu, 84 · 150-92 Tern Harbor Rd Bsmt, Flushing 11354
Hero mirror: son promised Tuesday and came (kept event logged quietly).

- **DECOY** `s1_e_000319` h 39.0 (09-03T11:00) [visit_note] Visited Mrs. Liu, 84, 150-92 Tern Harbor Rd. Lives alone, basement flooded, no power. Son coming Tuesday to take her to his place.
- `s1_e_000782` h 139.0 (09-07T15:00) [visit_note] Back at 15092 Tern Harbor Rd: Mrs. Liu's son arrived, packing her things, she's going to Fort Lee with him.

### s1_d_04 · resolved_alarm · Rosa Delgado, 76 · 48-75 Kettlebrook Rd 3F, Woodside 11377
Misses calls for one day, answers the next and is fine.

- **DECOY** `s1_e_000194` h 17.0 (09-02T12:59) [311] 311 call from R. DELGADO at 4875 KETTLEBROOK RD: water in basement, senior resident.
- `s1_e_000693` h 111.0 (09-06T11:00) [visit_note] Checked on Mrs. Delgado at 48-75 Kettlebrook Rd: basement dried out, she is fine. Missed our call yesterday, she was at the laundromat.

### s1_d_05 · resolved_alarm · Rosa Gonzalez, 45 · 42-16 Emberwood Ave Bsmt, Elmhurst 11373
Gas smell; no leak found the same evening.

- **DECOY** `s1_e_000526` h 70.0 (09-04T18:00) [311] 311 call from ROSA GONZÁLEZ at 42-16 EMBERWOOD AVE: smell of gas in basement after flood.
- `s1_e_000538` h 72.5 (09-04T20:29) [crew] Con Edison gas crew at 42-16 EMBERWOOD AVE: no leak found, odor from wet boiler room, cleared.

### s1_d_06 · resolved_alarm · Abdul Begum, 38 · 55-60 Driftwood Row Bsmt, Corona 11368
Sewage with kids; cleared next day, corrected Sep 6.

- **DECOY** `s1_e_000291` h 36.0 (09-03T08:00) [311] 311 call at 5560 DRIFTWOOD ROW: sewage backing up into apartment, 2 kids at home.
- `s1_e_000442` h 62.0 (09-04T09:59) [crew] DEP crew cleared sewer line at 55-60 DRIFTWOOD ROW.
- `s1_e_000713` h 114.0 (09-06T14:00) [crew] HPD reinspection at 55-60 DRIFTWOOD ROW: unit cleaned and sanitized by landlord, condition corrected.

### s1_d_07 · kept_promise · Rafiq Hossain, 80 · 164-70 Nettlefield Rd 2R, Jamaica 11432
No food; meals delivered the same afternoon.

- **DECOY** `s1_e_000573` h 86.0 (09-05T09:59) [visit_note] Rafiq Hossein, 164-70 Nettlefield Rd: no food in the house, fridge spoiled. Red Cross will bring meals this afternoon.
- `s1_e_000643` h 91.0 (09-05T15:00) [crew] Red Cross ERV: delivered meals and water to 164-70 NETTLEFIELD RD.

### s1_d_08 · resolved_alarm · Xiu Ying Lin, 83 · 29-09 Saltmarsh Way 2F, Flushing 11358
Not seen for days; wellness check finds her fine.

- **DECOY** `s1_e_000946` h 213.0 (09-10T17:00) [311] 311 call from neighbor at 29-09 SALTMARSH WAY: elderly neighbor not seen in days, lights off.
- `s1_e_000970` h 229.0 (09-11T09:00) [crew] NYPD wellness check at 29-09 SALTMARSH WAY: resident fine, was staying with her sister in Bayside, now home.

### s1_d_09 · namesake · Hong Wang, 58 · 43-41 Quailbrook St 3F, Elmhurst 11373
Same surname, same building as s1_n_07, different unit (3F); fine.

- **DECOY** `s1_e_000703` h 112.0 (09-06T12:00) [visit_note] Mrs. Wang, 43-41 Quailbrook St 3F: upstairs unit dry, power back, doing fine, helping neighbors.

### s1_d_10 · restored_outage · Maria Gonzalez, 70 · 96-06 Cindermoss Ln 1F, Corona 11368
Maria Gonzalez (1F): no power, restored next day.

- **DECOY** `s1_e_000320` h 39.0 (09-03T11:00) [311] 311 call from MARIA GONZALEZ at 9606 CINDERMOSS LN 1F: no power, water in the building.
- `s1_e_000507` h 68.0 (09-04T15:59) [crew] Con Edison field crew: service restored at 96-06 CINDERMOSS LN 1F, basement pumped by owner.

### s1_d_11 · namesake · Ana Gonzalez, 44 · 96-06 Cindermoss Ln Bsmt, Corona 11368
Ana Gonzalez (basement), same building as s1_d_10; must not merge.

- **DECOY** `s1_e_000704` h 112.0 (09-06T12:00) [visit_note] Mrs. Gonzales at 96-06 Cindermoss Ln Bsmt, cleanup done, doing fine.
