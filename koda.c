#include <Adafruit_NeoPixel.h>
#include <ETH.h>
#include <ArtnetEther.h>

#define NUM_LEDS 9       
#define EXT_LED  41       

Adafruit_NeoPixel strip1(NUM_LEDS, EXT_LED, NEO_GRB + NEO_KHZ800);

// ARtnet
ArtnetReceiver artnet;
const int universeStart = 0;
const int universeCount = 3;
const int steviloLED = 3;

void onDmxFrame(const uint8_t* data, uint16_t size, const ArtDmxMetadata& metadata, const ArtNetRemoteInfo& remote) {
  uint16_t universe = metadata.universe;
  Serial.printf("ArtNet Universe: %d, Size: %d\n", universe, size);
  Serial.printf("First RGB: %d %d %d\n", data[0], data[1], data[2]);

  int ledStart = (universe - universeStart) * steviloLED;
  
  for(int i = 0; i < steviloLED; i++) {
    int dmxIndex = i * 3;
    if(dmxIndex + 2 >= size) break;
    if(ledStart + i >= NUM_LEDS) break;

    uint8_t R = data[dmxIndex];
    uint8_t G = data[dmxIndex + 1];
    uint8_t B = data[dmxIndex + 2];

    strip1.setPixelColor(ledStart + i, strip1.Color(R, G, B));
  }
  strip1.show();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting Ethernet...");
  ETH.begin();

  while (!ETH.linkUp()) {
    delay(100);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("IP address: ");
  Serial.println(ETH.localIP());

  strip1.begin();
  strip1.setBrightness(50);
  strip1.show();

  artnet.begin();

  for(int i = 0; i < universeCount; i++) {
    artnet.subscribeArtDmxUniverse(universeStart + i, onDmxFrame);
  }
}

void loop() {
  artnet.parse();
}
