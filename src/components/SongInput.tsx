import React, { useState } from 'react';
import { Search, Upload, Music } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';

interface SongInputProps {
  onSearch: (query: string) => void;
}

export function SongInput({ onSearch }: SongInputProps) {
  const [inputValue, setInputValue] = useState('');
  const [inputMethod, setInputMethod] = useState<'search' | 'upload'>('search');

  const handleSearch = () => {
    if (inputValue.trim()) {
      onSearch(inputValue.trim());
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-semibold text-gray-800 mb-2">
          Find Your Perfect Musical Match
        </h2>
        <p className="text-gray-600">
          Enter a song name or upload an audio file to discover similar tracks
        </p>
      </div>

      {/* Input Method Toggle */}
      <div className="flex justify-center">
        <div className="flex bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setInputMethod('search')}
            className={`px-4 py-2 rounded-md flex items-center gap-2 transition-all ${
              inputMethod === 'search'
                ? 'bg-white text-purple-600 shadow-sm'
                : 'text-gray-600 hover:text-purple-600'
            }`}
          >
            <Search className="w-4 h-4" />
            Search by Name
          </button>
          <button
            onClick={() => setInputMethod('upload')}
            className={`px-4 py-2 rounded-md flex items-center gap-2 transition-all ${
              inputMethod === 'upload'
                ? 'bg-white text-purple-600 shadow-sm'
                : 'text-gray-600 hover:text-purple-600'
            }`}
          >
            <Upload className="w-4 h-4" />
            Upload Audio
          </button>
        </div>
      </div>

      {/* Search Input */}
      {inputMethod === 'search' && (
        <div className="space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <Input
              type="text"
              placeholder="e.g., 'Bohemian Rhapsody by Queen' or 'Shape of You'"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              className="pl-10 py-3 text-lg"
            />
          </div>
          <Button 
            onClick={handleSearch}
            disabled={!inputValue.trim()}
            className="w-full py-3 text-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700"
          >
            Find Similar Songs
          </Button>
        </div>
      )}

      {/* Upload Interface */}
      {inputMethod === 'upload' && (
        <div className="space-y-4">
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-purple-400 transition-colors">
            <div className="flex flex-col items-center gap-4">
              <div className="p-4 bg-purple-100 rounded-full">
                <Music className="w-8 h-8 text-purple-600" />
              </div>
              <div>
                <p className="text-lg font-medium text-gray-800 mb-1">
                  Drop your audio file here
                </p>
                <p className="text-gray-600">
                  Supports MP3, WAV, FLAC files up to 10MB
                </p>
              </div>
              <Button variant="outline" className="mt-2">
                <Upload className="w-4 h-4 mr-2" />
                Choose File
              </Button>
            </div>
          </div>
          <p className="text-sm text-gray-500 text-center">
            Note: Audio upload functionality requires backend integration
          </p>
        </div>
      )}

      {/* Popular Examples */}
      <div className="bg-gray-50 rounded-lg p-4">
        <p className="text-sm font-medium text-gray-700 mb-2">Try these popular examples:</p>
        <div className="flex flex-wrap gap-2">
          {[
            'Blinding Lights - The Weeknd',
            'Don\'t Stop Believin\' - Journey',
            'Imagine - John Lennon',
            'Thriller - Michael Jackson'
          ].map((example) => (
            <button
              key={example}
              onClick={() => {
                setInputValue(example);
                setInputMethod('search');
              }}
              className="px-3 py-1 bg-white border border-gray-200 rounded-full text-sm text-gray-600 hover:text-purple-600 hover:border-purple-200 transition-colors"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}