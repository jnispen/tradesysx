### GetQuotes

When run GetQuotes will perform the following steps:
- download historical stock data from Yahoo Finance
- from the configured mechanical trading rules, generate ENTER and EXIT signals for the individual stocks
- do a balance calculation based on the generated trades and position sizing strategy (i.e. run a paper trade simulation)
- run a MonteCarlo simulation of the R-multiple distribution obtained from the trading system and generate a plot of possible outcomes
- save data, generate plots and reports for all the steps mentioned
- (if configured) publish a summary of the results on a (private) telegram channel

The script was directly inspired by the various books on trading systems development written by Dr. Van K. Tharp.

#### Setup
