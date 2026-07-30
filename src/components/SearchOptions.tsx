import React from 'react';
import { AudioWaveform, FileText, Music } from 'lucide-react';

interface SearchOptionsProps {
  searchType: 'melody' | 'lyrics' | 'both';
  onSearchTypeChange: (type: 'melody' | 'lyrics' | 'both') => void;
}

export function SearchOptions({ searchType, onSearchTypeChange }: SearchOptionsProps) {

  const options = [
    {
      id: 'melody' as const,
      label: 'Melody Only',
      icon: AudioWaveform,
      description: 'Match musical patterns and rhythm'
    },
    {
      id: 'lyrics' as const,
      label: 'Lyrics Only',
      icon: FileText,
      description: 'Match themes and lyrical content'
    },
    {
      id: 'both' as const,
      label: 'Both',
      icon: Music,
      description: 'Best overall match'
    }
  ];

  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-gray-800">Search by:</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {options.map((option) => {
          const Icon = option.icon;
          const isSelected = searchType === option.id;
          
          return (
            <button
              key={option.id}
              onClick={() => onSearchTypeChange(option.id)}
              className={`p-4 rounded-lg border-2 transition-all text-left ${
                isSelected
                  ? option.id === 'melody'
                    ? 'border-purple-500 bg-purple-50 ring-2 ring-purple-200'
                    : option.id === 'lyrics'
                    ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-200'
                    : 'border-violet-500 bg-violet-50 ring-2 ring-violet-200'
                  : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
              }`}
            >
              <div className="flex items-start gap-3">
                <div className={`p-2 rounded-lg ${
                  isSelected
                    ? option.id === 'melody'
                      ? 'bg-purple-100'
                      : option.id === 'lyrics'
                      ? 'bg-indigo-100'
                      : 'bg-violet-100'
                    : 'bg-gray-100'
                }`}>
                  <Icon className={`w-5 h-5 ${
                    isSelected
                      ? option.id === 'melody'
                        ? 'text-purple-600'
                        : option.id === 'lyrics'
                        ? 'text-indigo-600'
                        : 'text-violet-600'
                      : 'text-gray-600'
                  }`} />
                </div>
                <div className="flex-1">
                  <div className={`font-medium ${
                    isSelected
                      ? option.id === 'melody'
                        ? 'text-purple-800'
                        : option.id === 'lyrics'
                        ? 'text-indigo-800'
                        : 'text-violet-800'
                      : 'text-gray-800'
                  }`}>
                    {option.label}
                  </div>
                  <div className={`text-sm ${
                    isSelected
                      ? option.id === 'melody'
                        ? 'text-purple-600'
                        : option.id === 'lyrics'
                        ? 'text-indigo-600'
                        : 'text-violet-600'
                      : 'text-gray-600'
                  }`}>
                    {option.description}
                  </div>
                </div>
                {isSelected && (
                  <div className={`w-3 h-3 rounded-full ${
                    option.id === 'melody'
                      ? 'bg-purple-500'
                      : option.id === 'lyrics'
                      ? 'bg-indigo-500'
                      : 'bg-violet-500'
                  }`} />
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}